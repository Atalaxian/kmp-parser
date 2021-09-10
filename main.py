import time
import re
import textwrap
import requests
from bs4 import BeautifulSoup
from main_window import Ui_Form
from PyQt5.QtWidgets import QApplication, QWidget, QFileDialog
from PyQt5.QtCore import QThread
from PyQt5 import QtCore


class Story:
    def __init__(self, text_story: str, set_text_story: set):
        self.text_story = text_story
        self.set_text_story = set_text_story
        self.valid = True


class WebParser(QtCore.QObject):
    mysignal = QtCore.pyqtSignal(int, bool, str)
    finished = QtCore.pyqtSignal()

    def __init__(self, stories: list):
        super().__init__()
        self.stories = stories

    # метод, который будет выполнять алгоритм в другом потоке
    def run(self):
        for page in self.stories:
            r = requests.get(f'https://killpls.me/story/{page}')
            if r.url != f'https://killpls.me/story/{page}':
                self.mysignal.emit(page, False, 'Произошло перенаправление')
                continue
            raw_text = r.content.replace(b"\r", b"")
            soup = BeautifulSoup(raw_text.decode('UTF-8'), 'lxml')
            for div in soup.find_all('div', style=lambda value: value and 'margin:0.5em 0' in value):
                replaced_text = div.text.replace('\n', '')
                self.mysignal.emit(page, True, replaced_text)
        self.finished.emit()


class Window(QWidget, Ui_Form):
    list_story = list()
    story_with_coincidence = list()
    keywords = list()
    list_thread = list()
    list_parser = list()
    diff = None
    st_time = None
    all_keywords_in = False
    count_loaded_story = 0
    count_quit_threads = 0

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setWindowTitle('Веб-парсер')
        self.load_data_from_net_ui.clicked.connect(self.start_load_data)
        self.start_analysis_ui.clicked.connect(self.analysis)
        self.save_story_ui.clicked.connect(self.save_story_with_coincidence)
        self.save_logs_ui.clicked.connect(self.save_logs)
        self.all_keywords_ui.stateChanged.connect(self.state_changed)

    @staticmethod
    def get_sequence_by_threads(start_value, end_value, count_threads) -> list:
        list_values = [[] for _ in range(count_threads)]
        for element in range(start_value, end_value + 1):
            list_values[element % count_threads].append(element)
        return list_values

    def reset_under_load(self) -> None:
        self.count_loaded_story = 0
        self.count_quit_threads = 0
        self.progress_bar_ui.setValue(0)
        self.text_browser_ui.clear()
        self.list_story.clear()
        for thread in self.list_thread:
            thread.quit()
            thread.wait()
            del thread
        self.list_thread.clear()
        self.list_parser.clear()

    def reset_under_analysis(self) -> None:
        self.story_with_coincidence.clear()
        self.result_text_box_ui.clear()

    @QtCore.pyqtSlot()
    def start_load_data(self) -> None:
        self.reset_under_load()
        start_story = self.start_story_ui.value()
        end_story = self.end_story_ui.value()
        count_threads = self.count_threads_ui.value()
        if start_story > end_story:
            return
        self.set_state_buttons(True)
        self.diff = (end_story - start_story) + 1
        self.st_time = time.time()
        sequence = self.get_sequence_by_threads(start_story, end_story, count_threads)
        for offset in range(count_threads):
            parser = WebParser(sequence[offset])
            self.list_parser.append(parser)
            thread = QThread()
            self.list_thread.append(thread)
            parser.moveToThread(thread)
            parser.mysignal.connect(self.add_new_item_from_net)
            parser.finished.connect(self.on_finished)
            thread.started.connect(parser.run)
            thread.start()

    def set_state_buttons(self, disabled: bool) -> None:
        self.load_data_from_net_ui.setDisabled(disabled)
        self.save_logs_ui.setDisabled(disabled)
        self.start_analysis_ui.setDisabled(disabled)
        self.save_story_ui.setDisabled(disabled)
        self.count_threads_ui.setDisabled(disabled)

    @QtCore.pyqtSlot(int)
    def state_changed(self, state: int) -> None:
        if state == 2:
            self.all_keywords_in = True
        else:
            self.all_keywords_in = False

    @QtCore.pyqtSlot()
    def on_finished(self):
        self.count_quit_threads += 1
        if self.count_quit_threads == self.count_threads_ui.value():
            self.text_browser_ui.append(f'Всего ушло времени на обработку: {time.time() - self.st_time:.2f}')
            self.text_browser_ui.append(f'Всего попыток загрузить истории: {self.count_loaded_story}')
            self.set_state_buttons(False)

    @QtCore.pyqtSlot(int, bool, str)
    def add_new_item_from_net(self, number_page, result, story):
        self.count_loaded_story += 1
        self.progress_bar_ui.setValue(int((self.count_loaded_story / self.diff) * 100))
        if result is False:
            self.text_browser_ui.append(f'Не удалось загрузить данные со страницы {number_page}. {story}')
        else:
            self.text_browser_ui.append(f'Загружена история №{number_page}')
            self.list_story.append(story.lstrip())

    @QtCore.pyqtSlot()
    def analysis(self):
        self.reset_under_analysis()
        num_analysis_story = 0
        num_story_with_coincidence = 0
        num_remove_story_with_filter = 0
        list_story = list()
        for story in self.list_story.copy():
            cleared_text = re.sub(r'[^\w\s]', ' ', story.lower())
            set_text_story = set(cleared_text.split())
            list_story.append(Story(story, set_text_story))
        start_keywords = [x.lower().replace(' ', '') for x in self.keywords_ui.toPlainText().split(',')]
        # Фильтрация по заданным правилам
        for keyword in start_keywords:
            if '|' in keyword:
                list_filter_values = [x for x in re.sub(r'[^\w\s]', ',', keyword).split(',')]
                set_filter_keywords = set(list_filter_values)
                for elem in list_story:
                    if set_filter_keywords.isdisjoint(elem.set_text_story):
                        elem.valid = False
                        num_remove_story_with_filter += 1
                start_keywords.remove(keyword)
        keywords = set(start_keywords)
        if len(keywords) == 0:
            for story in list_story:
                if story.valid:
                    self.story_with_coincidence.append(story)
                    num_analysis_story += 1
                    num_story_with_coincidence += 1
            self.write_text_box_analysis(num_remove_story_with_filter, num_analysis_story, num_story_with_coincidence)
            return
        for story in list_story:
            if not story.valid:
                continue
            if self.all_keywords_in:
                if keywords.issubset(story.set_text_story):
                    self.story_with_coincidence.append(story)
                    num_story_with_coincidence += 1
            else:
                if not story.set_text_story.isdisjoint(keywords):
                    self.story_with_coincidence.append(story)
                    num_story_with_coincidence += 1
            num_analysis_story += 1
        self.write_text_box_analysis(num_remove_story_with_filter, num_analysis_story, num_story_with_coincidence)

    def write_text_box_analysis(self, num_remove_story_with_filter: int,
                                num_analysis_story: int, num_story_with_coincidence: int) -> None:
        self.result_text_box_ui.append(f'Удалено историй при заданных фильтрах: {num_remove_story_with_filter}')
        self.result_text_box_ui.append(f'Проанализировано историй: {num_analysis_story}')
        self.result_text_box_ui.append(f'Найдено совпадений: {num_story_with_coincidence}')

    @QtCore.pyqtSlot()
    def save_logs(self) -> None:
        file_path = QFileDialog.getSaveFileName(self, "Выбрать файл", "log",
                                                "*.txt;;")[0]
        if file_path != '':
            with open(file_path, 'w') as file:
                file.write(self.text_browser_ui.toPlainText())

    @QtCore.pyqtSlot()
    def save_story_with_coincidence(self) -> None:
        file_path = QFileDialog.getSaveFileName(self, "Выбрать файл", "",
                                                "*.txt;;")[0]
        if file_path != '':
            with open(file_path, 'w') as file:
                for story in self.story_with_coincidence:
                    file.write(textwrap.fill(story.text_story, width=160))
                    file.write('\n\n')


if __name__ == '__main__':
    import sys

    app = QApplication(sys.argv)
    w = Window()
    w.show()
    sys.exit(app.exec())
