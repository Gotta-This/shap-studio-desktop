"""Statically inspect the frozen scientific engine; never execute the binary."""
import argparse
import json
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader

QT_BINDINGS = ('pyside6', 'pyside2', 'pyqt6', 'pyqt5', 'shiboken6', 'shiboken2')
QT_LIBRARIES = ('qtcore', 'qtgui', 'qtwidgets', 'qtqml', 'qtquick', 'qtwebengine',
                'qt5core', 'qt5gui', 'qt5widgets', 'qt6core', 'qt6gui', 'qt6widgets')
LEGACY_GUI = ('app', 'hub', 'design_surface', 'manuscript_ui', 'sidebar', 'theme',
              'word_batch', 'data_tools', 'prose_table_ui', 'typed_field_ui',
              'editor_dialogs', 'date_picker', 'todo_ui', 'strict_ui', 'unified_preview')
UI_RESOURCES = ('penpot-layout.json', 'icon.png', 'icon.ico', 'icon.icns')


def audit(path):
    archive = CArchiveReader(str(path))
    files = list(archive.toc)
    modules = []
    for name in files:
        if name.lower().endswith('.pyz'):
            modules.extend(archive.open_embedded_archive(name).toc)
    qt = [name for name in files + modules if any(q in name.lower() for q in QT_BINDINGS + QT_LIBRARIES)]
    gui = [name for name in modules if any(name == 'clinical_studio.' + key or name.startswith('clinical_studio.' + key + '.') for key in LEGACY_GUI)]
    resources = [name for name in files if name.replace('\\', '/').startswith('clinical_studio/assets/') and name.replace('\\', '/').rsplit('/', 1)[-1] in UI_RESOURCES]
    return dict(binary=str(path), bytes=path.stat().st_size, file_count=len(files), module_count=len(modules),
                qt_runtime_entries=qt, legacy_gui_modules=gui, unused_ui_resources=resources,
                scientific_modules=[name for name in modules if name.startswith('clinical_studio')])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    parser.add_argument('--strict-resources', action='store_true')
    args = parser.parse_args()
    result = audit(args.binary)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result['qt_runtime_entries'] or result['legacy_gui_modules']:
        raise SystemExit('Frozen engine unexpectedly includes Qt or the legacy GUI.')
    if args.strict_resources and result['unused_ui_resources']:
        raise SystemExit('Frozen engine unexpectedly includes unused UI resources.')
