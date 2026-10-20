"""Read-only projection invariant audit, including exact native chunk planning."""
import json,sqlite3
from pathlib import Path
from types import SimpleNamespace
from .policy import PolicyError,authored_text,allowed_features

def audit(workspace,check_vectors=True):
    from basic_memory.repository.semantic_chunking import build_vector_chunk_records
    notes=workspace/'notes';db=workspace/'config/memory.db'
    if not db.exists():raise PolicyError('Managed database missing; initialize or repair first')
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row
        project=c.execute("SELECT id FROM project WHERE name='managed'").fetchone()
        if not project:raise PolicyError('Managed project missing')
        pid=project[0];entities=c.execute('SELECT * FROM entity WHERE project_id=?',(pid,)).fetchall()
        indexed={e['file_path'] for e in entities};files={str(p.relative_to(notes)) for p in notes.rglob('*.md')}
        if indexed!=files:raise PolicyError('Note/entity inventory differs; run managed sync')
        expected_keys=set();fts_count=0;obs_count=0;rel_count=0
        for e in entities:
            raw=(notes/e['file_path']).read_text();body=authored_text(raw);obs,rels=allowed_features(raw)
            rows=c.execute('SELECT * FROM search_index WHERE project_id=? AND entity_id=?',(pid,e['id'])).fetchall();base=[r for r in rows if r['type']=='entity']
            if len(base)!=1 or (base[0]['content_snippet'] or '').strip()!=body:raise PolicyError('Dirty authored search projection: '+e['file_path']+'; run managed repair/sync')
            for r in rows:
                if r['type']=='observation':
                    if (r['category'] or 'Note',r['content_snippet'] or '') not in obs:raise PolicyError('Generated observation search row: '+e['file_path'])
                    obs_count+=1
                if r['type']=='relation':
                    rel=c.execute('SELECT relation_type,to_name FROM relation WHERE project_id=? AND id=?',(pid,r['id'])).fetchone()
                    if not rel or tuple(rel) not in rels:raise PolicyError('Generated relation search row: '+e['file_path'])
                    rel_count+=1
            plans=build_vector_chunk_records(SimpleNamespace(**dict(r)) for r in rows).records
            expected={(r['chunk_key'],r['chunk_text'],r['source_hash']) for r in plans}
            if check_vectors:
                actual={tuple(r) for r in c.execute('SELECT chunk_key,chunk_text,source_hash FROM search_vector_chunks WHERE project_id=? AND entity_id=?',(pid,e['id']))}
                if actual!=expected:raise PolicyError('Vector input differs from authored FTS projection: '+e['file_path'])
            expected_keys.update((e['id'],r[0]) for r in expected);fts_count+=len(rows)
        if check_vectors:
            import sqlite_vec
            c.enable_load_extension(True);sqlite_vec.load(c);c.enable_load_extension(False)
            physical={r[0] for r in c.execute('SELECT rowid FROM search_vector_embeddings')}
            chunk_ids={r[0] for r in c.execute('SELECT id FROM search_vector_chunks WHERE project_id=?',(pid,))}
            if physical!=chunk_ids:raise PolicyError('Vector input/chunk physical storage differs; run managed repair')
            if c.execute("SELECT count(*) FROM search_vector_chunks WHERE project_id=? AND embedding_status!='ready'",(pid,)).fetchone()[0]:raise PolicyError('Vector input not fully embedded')
        graph=c.execute('SELECT count(*),sum(to_id IS NULL) FROM relation WHERE project_id=?',(pid,)).fetchone()
        return {'passed':True,'notes':len(files),'fts_rows':fts_count,'authored_observation_rows':obs_count,'authored_relation_rows':rel_count,'vector_chunks':len(expected_keys),'graph_edges':graph[0],'unresolved_edges':graph[1] or 0,'physical_vectors_verified':check_vectors}
