"""Optional structured findings; legacy strings retain their original meaning."""
from pathlib import Path
import hashlib
from .artifacts import ArtifactError


def validate(findings):
    if not isinstance(findings, list):
        raise ArtifactError('findings must be an array')
    for item in findings:
        if isinstance(item, str):
            continue
        if not isinstance(item, dict) or not all(item.get(k) for k in ('id', 'message', 'evidence', 'anchor')):
            raise ArtifactError('Structured findings require id, message, evidence and anchor')
        anchor = item['anchor']
        if not isinstance(anchor, dict) or anchor.get('type') not in {'artifact', 'code'}:
            raise ArtifactError('Finding anchor type must be artifact or code')
        if anchor['type'] == 'artifact':
            ref = anchor.get('reference')
            if not isinstance(ref, dict) or set(ref) != {'path', 'revision'}:
                raise ArtifactError('Artifact finding requires an exact reference')
        elif not all(isinstance(anchor.get(k), str) and anchor[k] for k in ('path', 'revision')):
            raise ArtifactError('Code finding requires path and SHA256 content revision')
        if not isinstance(item.get('resolution', {}), dict):
            raise ArtifactError('Finding resolution must be an object')
        if item.get('resolution', {}).get('state', 'open') in {'resolved', 'dismissed'} and not item['resolution'].get('evidence'):
            raise ArtifactError('Resolved or dismissed findings require resolution evidence')
        if item.get('resolution', {}).get('state', 'open') not in {'open', 'resolved', 'dismissed'}:
            raise ArtifactError('Unsupported finding resolution')
    return findings


def project(findings, artifacts, reference_status):
    rows = []
    for item in findings:
        if isinstance(item, str):
            rows.append({'message': item, 'anchor_status': 'unanchored', 'resolution': {'state': 'unknown'}})
            continue
        row = dict(item)
        try:
            validate([item])
            anchor = item['anchor']
            if anchor['type'] == 'artifact':
                status = reference_status(anchor['reference'])
            else:
                path = artifacts.project / anchor['path']
                if not path.resolve().is_relative_to(artifacts.project):
                    raise ArtifactError('Code anchor escapes project')
                status = 'current' if hashlib.sha256(path.read_bytes()).hexdigest() == anchor['revision'] else 'stale'
            row['anchor_status'] = status
        except (OSError, ValueError, TypeError, AttributeError) as error:
            row.update(anchor_status='unavailable', anchor_error=str(error))
        rows.append(row)
    return rows
