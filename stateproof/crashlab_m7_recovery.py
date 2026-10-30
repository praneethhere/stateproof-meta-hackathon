"""M7 service-error recovery runner, additive only. Does not modify frozen code.

This is an explicitly labeled follow-up batch after a prior uncheckpointed
Meta Model API failure, not a continuation of the original preregistered run.
Each completed episode is saved before the next model call. Failed episodes
remain incomplete and may be retried ONLY with an explicit --resume, with an
error journal that records the deviation. No rerun of successful episodes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid
from typing import Any
import re

from stateproof.crashlab import digest
from stateproof.crashlab_http import run_http_experiment
from stateproof.crashlab_recovery_eval import _verify_protocol, summarize

SCHEMA = 'stateproof-crashlab-m7-service-recovery-v1'


# Only the additive follow-up runner is instrumented; the frozen HTTP engine is unchanged.
# A response continuation can depend on Meta's server-side persistence layer.
# Do not retry HTTP 400 automatically: the previous model call or local tool may
# have made progress, and this is a scientific experiment.
def _safe_api_label(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 80:
        return None
    return value if re.fullmatch(r"[A-Za-z0-9_.\[\]-]+", value) else None


def _api_error_category(body: Any) -> str:
    if not isinstance(body, dict):
        return 'unspecified_400'
    detail = body.get('error', body)
    if not isinstance(detail, dict):
        return 'unspecified_400'
    msg = str(detail.get('message', ''))[:1500].lower()
    param = str(detail.get('param') or '').lower()
    if 'previous_response_id' in msg or 'previous response' in msg or ('response' in msg and ('not found' in msg or 'persist' in msg)):
        return 'response_history_reference'
    if 'call_id' in msg or 'function_call_output' in msg or 'conversation structure' in msg:
        return 'tool_call_history_structure'
    if 'context length' in msg or 'context window' in msg or 'max_output_tokens' in msg or param == 'max_output_tokens':
        return 'token_or_context_budget'
    if 'reasoning' in msg and ('invalid' in msg or 'format' in msg):
        return 'reasoning_item_format'
    if 'tool' in msg and ('invalid' in msg or 'unsupported' in msg):
        return 'tool_schema_or_choice'
    return 'unspecified_400'


class _AuditedResponses:
    """Pass through exact model requests; log only non-sensitive metadata on errors."""
    def __init__(self, actual: Any):
        self._actual = actual
        self._call_index = 0

    def create(self, **kwargs: Any) -> Any:
        self._call_index += 1
        try:
            return self._actual.create(**kwargs)
        except Exception as exc:
            body = getattr(exc, 'body', None)
            diagnostic = {
                'api_request_number_in_episode': self._call_index,
                'uses_previous_response_id': bool(kwargs.get('previous_response_id')),
                'input_is_tool_output_list': isinstance(kwargs.get('input'), list),
            }
            if isinstance(body, dict):
                detail = body.get('error', body)
                if isinstance(detail, dict):
                    for key, out_key in [('code', 'api_error_code'), ('type', 'api_error_type'), ('param', 'api_error_param')]:
                        safe = _safe_api_label(detail.get(key))
                        if safe is not None:
                            diagnostic[out_key] = safe
            if getattr(exc, 'status_code', None) == 400:
                diagnostic['api_error_category'] = _api_error_category(body)
            try:
                setattr(exc, '_crashlab_safe_diagnostic', diagnostic)
            except (AttributeError, TypeError):
                pass
            raise


class _AuditedClient:
    def __init__(self, actual: Any):
        self.responses = _AuditedResponses(actual.responses)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_new_json(path: Path, data: dict) -> None:
    """Create a receipt without ever replacing an existing receipt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as out:
        json.dump(data, out, indent=2, ensure_ascii=False)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())


def _journal(root: Path, event: dict) -> None:
    with (root / 'events.jsonl').open('a', encoding='utf-8') as out:
        out.write(json.dumps({'time_utc': utc(), **event}, ensure_ascii=False) + '\n')
        out.flush()
        os.fsync(out.fileno())


def _receipt_path(root: Path, position: int, case: str) -> Path:
    if not case.isidentifier():
        raise ValueError('Invalid case identifier')
    return root / f'{position + 1:02d}_{case}.json'


def _completed(root: Path, manifest: dict) -> list[dict]:
    rows = []
    for i, condition in enumerate(manifest['cases']):
        path = _receipt_path(root, i, condition['case'])
        if not path.exists():
            continue
        saved = json.loads(path.read_text(encoding='utf-8'))
        if (saved.get('schema') != SCHEMA or saved.get('manifest_sha256') != manifest['manifest_sha256']
                or saved.get('case') != condition['case'] or saved.get('ordinal') != i + 1):
            raise ValueError(f'Completed receipt metadata mismatch: {path}')
        episode = saved['episode']
        if digest({k: v for k, v in episode.items() if k != 'receipt_sha256'}) != episode.get('receipt_sha256'):
            raise ValueError(f'Completed episode digest mismatch: {path}')
        if (episode.get('actor') != 'muse' or episode.get('fault') != condition['fault']
                or episode.get('readback_fault', 'normal') != condition['readback_fault']
                or episode.get('guarded') != condition['guarded']):
            raise ValueError(f'Completed experiment configuration mismatch: {path}')
        expected = {'case': condition['case'], **summarize(episode)}
        if saved['row'] != expected:
            raise ValueError(f'Completed receipt summary mismatch: {path}')
        rows.append(expected)
    return rows


def _safe_error(exc: Exception) -> dict:
    """No raw exception, request body, model messages or API token in journal."""
    status = getattr(exc, 'status_code', None)
    reqid = getattr(exc, 'request_id', None)
    result: dict[str, Any] = {'exception_type': type(exc).__name__}
    if isinstance(status, int):
        result['http_status'] = status
    if isinstance(reqid, str) and len(reqid) <= 150:
        result['api_request_id'] = reqid
    diagnostic = getattr(exc, '_crashlab_safe_diagnostic', None)
    if isinstance(diagnostic, dict):
        allowed = {'api_request_number_in_episode', 'uses_previous_response_id',
                   'input_is_tool_output_list', 'api_error_code', 'api_error_type',
                   'api_error_param', 'api_error_category'}
        result.update({k: v for k, v in diagnostic.items() if k in allowed})
    return result


def _status(root: Path, manifest: dict) -> dict:
    rows = _completed(root, manifest)
    done = {r['case'] for r in rows}
    return {
        'schema': SCHEMA,
        'status': 'COMPLETE' if len(rows) == len(manifest['cases']) else 'PARTIAL',
        'evidence_type': 'FOLLOW_UP_AFTER_EXTERNAL_503_NOT_ORIGINAL_FROZEN_FIRST_RUN',
        'manifest_sha256': manifest['manifest_sha256'],
        'completed': len(rows), 'planned': len(manifest['cases']),
        'remaining_cases': [c['case'] for c in manifest['cases'] if c['case'] not in done],
        'rows': rows,
        'last_updated_utc': utc(),
        'limitations': [
            'First preregistered live attempt aborted with Meta API 503 and had no per-case checkpoints',
            'This independently labeled follow-up re-executes the frozen conditions',
            'Completed episodes are not rerun; failed in-progress episodes may need new attempts',
            'One synthetic operation; one model sample per completed condition',
            'Local hashes detect changes, not independent cryptographic attestation',
        ],
    }


def run(freeze_path: Path, output_dir: Path, *, accept_api_cost=False, resume=False,
        check_only=False, execute=run_http_experiment) -> dict:
    manifest, data = _verify_protocol(freeze_path)
    root = output_dir.resolve()
    # Only write below gitignored evidence/ to avoid accidentally publishing records.
    evidence = Path('evidence').resolve()
    if not root.is_relative_to(evidence) or root == evidence:
        raise ValueError('Output directory must be under ./evidence/')
    manifest_file = root / 'batch.json'
    if check_only:
        if root.exists() and manifest_file.exists():
            stored = json.loads(manifest_file.read_text(encoding='utf-8'))
            if stored['manifest_sha256'] != manifest['manifest_sha256']:
                raise ValueError('Existing recovery batch belongs to another frozen manifest')
            return _status(root, manifest)
        return {'status': 'READY', 'evidence_type': 'FOLLOW_UP_AFTER_EXTERNAL_503',
                'manifest_sha256': manifest['manifest_sha256'],
                'planned': len(manifest['cases']), 'existing_batch': root.exists()}
    if not accept_api_cost:
        raise ValueError('Requires explicit --accept-api-cost to make live Meta API requests')
    if root.exists():
        if not resume:
            raise FileExistsError('Output directory exists. Use --resume explicitly; do not overwrite.')
        if not manifest_file.exists():
            raise ValueError('Existing directory lacks recovery batch manifest')
        stored = json.loads(manifest_file.read_text(encoding='utf-8'))
        if stored['manifest_sha256'] != manifest['manifest_sha256']:
            raise ValueError('Frozen manifest mismatch')
    else:
        root.mkdir(parents=True, exist_ok=False)
        _write_new_json(manifest_file, {
            'schema': SCHEMA, 'batch_id': uuid.uuid4().hex, 'created_utc': utc(),
            'manifest_sha256': manifest['manifest_sha256'],
            'frozen_protocol_path': str(freeze_path),
            'run_classification': 'FOLLOW_UP_AFTER_UNCHECKPOINTED_META_503',
            'declared_deviation': 'Original six-case live run aborted before final output was written',
            'protocol_changes': 'NONE',
        })
    done = {r['case'] for r in _completed(root, manifest)}
    _journal(root, {'type': 'BATCH_STARTED_OR_RESUMED', 'remaining': len(manifest['cases']) - len(done)})
    for index, condition in enumerate(manifest['cases']):
        if condition['case'] in done:
            continue
        case = condition['case']
        _journal(root, {'type': 'CASE_STARTED', 'case': case})
        plan = {
            'operation_id': manifest['operation_id'],
            'phase': condition['fault'],
            'hypothesis': 'Test one fixed synthetic commit-boundary failure with a private state oracle.',
            'readback': 'Inspect ledger; a read path may be stale or unavailable.',
        }
        try:
            arguments = dict(actor='muse', guarded=condition['guarded'],
                             effort=manifest['effort'], readback_fault=condition['readback_fault'])
            if execute is run_http_experiment:
                # Same Meta settings as muse_actor's default client, just wrapped for
                # error metadata. No automatic retries, no API-body logging.
                from openai import OpenAI
                key = os.getenv('MODEL_API_KEY')
                if not key:
                    raise RuntimeError('MODEL_API_KEY missing')
                arguments['client'] = _AuditedClient(OpenAI(
                    base_url='https://api.meta.ai/v1', api_key=key,
                    timeout=65, max_retries=0))
            episode = execute(data, plan, **arguments)
        except Exception as exc:
            _journal(root, {'type': 'CASE_ERROR_INCOMPLETE', 'case': case, **_safe_error(exc)})
            status = _status(root, manifest)
            _write_new_json(root / f'error_{uuid.uuid4().hex[:12]}.json', {
                'case': case, 'time_utc': utc(), 'status': 'INCOMPLETE', **_safe_error(exc),
                'note': 'No agent score for this case; in-progress local service state not preserved.'
            })
            # Do not silently continue or retry the failed episode.
            raise RuntimeError(
                f'Incomplete case {case}: {type(exc).__name__}; {status["completed"]} completed '
                f'episodes checkpointed under {root}. Explicit --resume required to rerun only incomplete cases.'
            ) from None
        row = {'case': case, **summarize(episode)}
        _write_new_json(_receipt_path(root, index, case), {
            'schema': SCHEMA, 'manifest_sha256': manifest['manifest_sha256'],
            'case': case, 'ordinal': index + 1, 'row': row, 'episode': episode,
        })
        _journal(root, {'type': 'CASE_COMPLETED', 'case': case, 'receipt_sha256': episode['receipt_sha256']})
        status = _status(root, manifest)
        _journal(root, {'type': 'CHECKPOINT', 'completed': status['completed']})
        print(f'Checkpoint saved: {case} ({status["completed"]}/{status["planned"]})', flush=True)
    _journal(root, {'type': 'BATCH_COMPLETED'})
    return _status(root, manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description='M7 follow-up, checkpointed evaluation after Meta 503')
    parser.add_argument('--freeze', type=Path, default=Path('evidence/m7/frozen_protocol.json'))
    parser.add_argument('--out-dir', type=Path, default=Path('evidence/m7/live_recovery_after_503'))
    parser.add_argument('--check-only', action='store_true', help='Validate frozen protocol and existing receipts. No API calls.')
    parser.add_argument('--accept-api-cost', action='store_true', help='Authorize live model calls')
    parser.add_argument('--resume', action='store_true', help='Resume only incomplete cases of an existing batch')
    args = parser.parse_args()
    result = run(args.freeze, args.out_dir, accept_api_cost=args.accept_api_cost,
                 resume=args.resume, check_only=args.check_only)
    # Only summary; raw episodes saved under ignored evidence/.
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
