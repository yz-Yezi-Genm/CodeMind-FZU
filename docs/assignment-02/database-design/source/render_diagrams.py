"""Render documentation views of the frozen model; never create a database."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from sqlalchemy import Uuid

from models import MODEL_TABLES, metadata

BASE = Path(__file__).resolve().parents[1]
FIGURES = BASE / 'figures'
GROUPS = {
    'core': ('知识库核心', ['knowledge_categories', 'knowledge_documents', 'document_versions', 'document_files', 'applicability_rules', 'applicability_rule_values', 'knowledge_chunks']),
    'governance': ('资料治理', ['business_directions', 'document_business_directions', 'verification_records', 'verification_tasks', 'document_milestones', 'document_file_sources', 'document_version_relations']),
    'interaction': ('交互与结果', ['users', 'conversation_sessions', 'interaction_messages', 'agent_tasks', 'task_results', 'result_citations', 'message_result_links']),
    'feedback': ('反馈', ['answer_feedback', 'feedback_review_links']),
}

def foreign_keys():
    return [(table, fk) for _, table in MODEL_TABLES
            for fk in sorted(table.foreign_key_constraints, key=lambda value: value.name)]

def browser_path(explicit=None):
    candidates = [explicit, os.environ.get('CODEMIND_BROWSER_PATH'),
                  shutil.which('chrome'), shutil.which('msedge'), shutil.which('chromium'),
                  r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                  r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                  '/usr/bin/chromium', '/usr/bin/google-chrome']
    for value in candidates:
        if value and Path(value).is_file():
            return str(Path(value).resolve())
    raise FileNotFoundError('渲染图形需要Chrome/Edge/Chromium；请设置CODEMIND_BROWSER_PATH或--browser。')

def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8', newline='\n')

def make_sources():
    FIGURES.mkdir(exist_ok=True)
    # Diagram views share the approved schema; the upstream er/ assets stay unchanged.
    overview = ['flowchart TB', '    accTitle: Complete CodeMind Database Relationship Overview',
                '    accDescr: All twenty three tables grouped by domain with forty foreign key groups. F numbers match Appendix B.']
    for key, (title, names) in GROUPS.items():
        overview.append(f'    subgraph {key}["{title}"]')
        overview.append('        direction LR')
        for name in names:
            label = name.replace('_', '_<br/>')
            overview.append(f'        {name}["{label}"]')
        overview.append('    end')
    for i, (table, fk) in enumerate(foreign_keys(), 1):
        parent = fk.elements[0].column.table.name
        overview.append(f'    {parent} -->|F{i:02}| {table.name}')
    write(FIGURES / 'overview.mmd', '\n'.join(overview) + '\n')

    views = {key: names for key, (_, names) in GROUPS.items() if key != 'feedback'}
    views['concept'] = ['knowledge_categories', 'knowledge_documents', 'document_versions', 'document_files', 'applicability_rules', 'knowledge_chunks']
    views['feedback'] = ['interaction_messages', 'document_versions', 'answer_feedback', 'feedback_review_links', 'verification_tasks']
    for key, names in views.items():
        lines = ['erDiagram', f'    accTitle: CodeMind {key.title()} Relational View',
                 '    accDescr: Selected key fields and within domain foreign keys. Complete cross domain constraints are listed in Appendix B.']
        for name in names:
            table = metadata.tables[name]
            lines.append('    ' + name + ' {')
            selected = [c for c in table.c if c.primary_key or c.foreign_keys]
            for column in selected:
                tags = ','.join(tag for flag, tag in [(column.primary_key, 'PK'), (bool(column.foreign_keys), 'FK')] if flag)
                typ = 'uuid' if isinstance(column.type, Uuid) else 'string'
                lines.append(f'        {typ} {column.name} {tags} "' + ('nullable' if column.nullable else 'required') + '"')
            lines.append('    }')
        for i, (table, fk) in enumerate(foreign_keys(), 1):
            parent = fk.elements[0].column.table.name
            if table.name in names and parent in names:
                optional = any(element.parent.nullable for element in fk.elements)
                lines.append(f'    {parent} ' + ('o|' if optional else '||') + f'--o{{ {table.name} : "F{i:02}"')
        write(FIGURES / (key + '.mmd'), '\n'.join(lines) + '\n')

def render(browser=None, force=False):
    make_sources()
    # Existing rendered assets make the checked-in PDF toolchain offline-capable.
    sources = list(FIGURES.glob('*.mmd'))
    manifest_path = FIGURES / 'render_manifest.json'
    import hashlib
    signature = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    old = {}
    if not force and manifest_path.is_file():
        old = json.loads(manifest_path.read_text(encoding='utf-8'))
        if old.get('profile') == 'formal-word-2' and old.get('source_sha256') == signature and all((p.with_suffix('.png')).is_file() and p.with_suffix('.svg').is_file() for p in sources):
            return
    custom_cli = os.environ.get('CODEMIND_MMDC')
    command = [custom_cli] if custom_cli else [shutil.which('npm.cmd') or shutil.which('npm') or 'npm', 'exec', '--yes', '--package', '@mermaid-js/mermaid-cli@11.12.0', '--', 'mmdc']
    env = dict(os.environ, PUPPETEER_SKIP_DOWNLOAD='true')
    with tempfile.TemporaryDirectory(prefix='codemind-mermaid-') as temporary:
        temporary = Path(temporary)
        config = temporary / 'config.json'
        write(config, json.dumps({'theme': 'base', 'themeVariables': {'fontFamily': 'SimSun, Microsoft YaHei, sans-serif', 'fontSize': '32px', 'primaryColor': '#ffffff', 'secondaryColor': '#ffffff', 'tertiaryColor': '#ffffff', 'primaryTextColor': '#000000', 'primaryBorderColor': '#333333', 'lineColor': '#333333'}, 'flowchart': {'htmlLabels': False, 'nodeSpacing': 36, 'rankSpacing': 65, 'curve': 'linear'}, 'er': {'fontSize': 23, 'nodeSpacing': 55, 'rankSpacing': 60}}, ensure_ascii=False))
        puppeteer = temporary / 'puppeteer.json'
        write(puppeteer, json.dumps({'executablePath': browser_path(browser)}))
        for source in sources:
            if not force and old.get('profile') == 'formal-word-2' and old.get('source_sha256',{}).get(source.name) == signature[source.name] and source.with_suffix('.png').is_file() and source.with_suffix('.svg').is_file():
                continue
            for extension in ('svg', 'png'):
                subprocess.run(command + ['-i', str(source), '-o', str(source.with_suffix('.' + extension)), '-c', str(config), '-p', str(puppeteer), '-w', '2600', '-H', '2000', '-s', '2', '-b', 'white'], env=env, check=True)
    write(manifest_path, json.dumps({'renderer': '@mermaid-js/mermaid-cli@11.12.0', 'profile': 'formal-word-2', 'source_sha256': signature}, ensure_ascii=False, indent=2) + '\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    render(args.browser, args.force)
