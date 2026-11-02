"""Offline integration checks for Qt/QML and its download bridge."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PySide6.QtCore import QUrl, QObject
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
import downloader
import qt_gui
APP =QApplication.instance() or QApplication([])
QQuickStyle.setStyle('Basic')


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.history = patch.object(qt_gui, 'load_history', return_value=[])
        self.history.start()
        self.addCleanup(self.history.stop)
        self.bridge = qt_gui.Bridge()

    def wait(self, key):
        for _ in range(100):
            APP.processEvents()
            if not self.bridge.state[key]:
                return
            QTest.qWait(10)
        self.fail('Background operation timed out')

    def test_analysis_failure_clears_busy(self):
        with patch.object(qt_gui, 'get_video_info', side_effect=ValueError('Vídeo privado')):
            self.bridge.analyze('https://youtube.com/watch?v=test')
            self.wait('searching')
        self.assertTrue(self.bridge.state['error'])
        self.assertIn('privado', self.bridge.state['status'])

    def test_url_change_cannot_download_previous_video(self):
        self.bridge.info = {'title': 'A'}
        self.bridge.analyzed_url = 'https://youtube.com/watch?v=A'
        with patch.object(qt_gui, 'download_video') as download:
            self.bridge.download('https://youtube.com/watch?v=B', 'mp4', '1080p', tempfile.gettempdir())
            download.assert_not_called()
        self.assertTrue(self.bridge.state['error'])

    def test_settings_persistence_and_failure(self):
        old = self.bridge.settings.copy()
        with patch.object(qt_gui, 'save_config') as save:
            self.bridge.saveSettings({'theme': 'light'})
            self.assertEqual(save.call_args.args[0]['theme'], 'light')
            self.assertEqual(self.bridge.config['theme'], 'light')
            self.assertEqual(self.bridge.settings['default_format'], old['default_format'])
        with patch.object(qt_gui, 'save_config', side_effect=OSError('Sin permiso')):
            self.bridge.saveSettings({'theme': 'dark'})
        self.assertEqual(self.bridge.config['theme'], 'light')
        self.assertTrue(self.bridge.state['error'])

    def test_update_check_failure_is_recoverable(self):
        with patch.object(qt_gui.updater, 'check_for_update', side_effect=OSError('Sin conexión')):
            self.bridge.checkUpdates()
            for _ in range(100):
                APP.processEvents()
                if self.bridge.state['updateState'] != 'checking':
                    break
                QTest.qWait(10)
        self.assertEqual(self.bridge.state['updateState'], 'error')
        with patch.object(qt_gui.updater, 'check_for_update', return_value=None):
            self.bridge.checkUpdates()
            for _ in range(100):
                APP.processEvents()
                if self.bridge.state['updateState'] != 'checking':
                    break
                QTest.qWait(10)
        self.assertEqual(self.bridge.state['updateState'], 'latest')

    def test_success_and_cancel_restore_controls(self):
        self.bridge.info = {'title': 'A'}
        self.bridge.analyzed_url = 'https://youtube.com/watch?v=A'
        self.bridge.settings['open_folder_after_download'] = False
        result = dict(title='A', format='mp4', quality='1080p', size_mb=1,
                      elapsed_seconds=1, output_path=tempfile.gettempdir())
        with patch.object(qt_gui, 'download_video', return_value=result), patch.object(qt_gui, 'save_entry') as save:
            self.bridge.download(self.bridge.analyzed_url, 'mp4', '1080p', tempfile.gettempdir())
            self.wait('downloading')
            save.assert_called_once()
        self.assertEqual(self.bridge.state['progress'], 1.)
        self.bridge.cancel.set()
        self.bridge.patch(downloading=True)
        self.bridge._receive('downloadError', 'cancelada')
        self.assertFalse(self.bridge.state['downloading'])
        self.assertFalse(self.bridge.state['error'])

    def test_convert_copies_only_compatible_mov(self):
        pp = downloader.ConvertVideoPP(None, 'mov')
        pp._copy_streams = True
        self.assertEqual(tuple(pp._options('mov'))[-2:], ('-c', 'copy'))
        pp._copy_streams = False
        self.assertIn('libx264', pp._options('mov'))
        self.assertIn('libxvid', pp._options('avi'))

    def test_failed_download_reports_reason_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'Otro.mp4').touch()
            with patch.object(downloader.yt_dlp, 'YoutubeDL') as ydl:
                def fail(url, download):
                    hook = ydl.call_args.args[0]['progress_hooks'][0]
                    hook({'status': 'downloading', 'filename': os.path.join(folder, 'A. B.f395.mp4')})
                    Path(folder, 'A. B.f395.mp4.part').touch()
                    Path(folder, 'A. B.temp.mov').touch()
                    raise ValueError('Conversion failed!')
                ydl.return_value.__enter__.return_value.extract_info.side_effect = fail
                with self.assertRaisesRegex(ValueError, 'Conversion failed'):
                    downloader.download_video('u', '360p', 'mov', folder)
            self.assertEqual(os.listdir(folder), ['Otro.mp4'])

    def test_qml_pages_and_themes(self):
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(str(i) for i in items))
        engine.rootContext().setContextProperty('backend', self.bridge)
        engine.load(QUrl.fromLocalFile(str(ROOT / 'src/qml/Main.qml')))
        self.assertTrue(engine.rootObjects())
        window = engine.rootObjects()[0]
        self.bridge.patch(info=dict(title='Título largo ' * 15, uploader='Canal', duration=128, formats=['1080p', '720p']),
                          history=[dict(title='Título largo ' * 20, format='MP3', quality='320kbps', date='23/10/2026', output_path='D:/Descargas', size_mb=4)])
        formats = window.findChild(QObject, 'formatSelect')
        quality = window.findChild(QObject, 'qualitySelect')
        formats.setProperty('currentIndex', 5)
        QTest.qWait(20)
        quality.setProperty('currentIndex', 1)
        self.bridge.patch(progress=.4, status='Descargando…')
        QTest.qWait(20)
        self.assertEqual(formats.property('currentText'), 'mp3')
        self.assertEqual(quality.property('currentText'), '192kbps')
        QQmlExpression(engine.rootContext(), formats, 'popup.open()').evaluate()
        QTest.qWait(20)
        QQmlExpression(engine.rootContext(), formats, 'popup.close()').evaluate()
        for theme in ['light', 'dark', 'system']:
            window.setProperty('theme', theme)
            for page in range(4):
                window.setProperty('page', page)
                QTest.qWait(50)
        window.close()
        self.assertEqual(warnings, [])
        engine.deleteLater()
        APP.processEvents()


if __name__ == '__main__':
    unittest.main()
