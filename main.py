# -*- coding: utf-8 -*-
"""
نظام أرشفة سجلات القيد - نسخة أندرويد (KivyMD)
نفس مميزات النسخة الأصلية (Tkinter) بواجهة متوافقة مع الموبايل:
- إضافة / تعديل / حذف سجل (اسم + رقم قيد + صورة)
- بحث فوري بالاسم أو رقم القيد
- اختيار صورة من المعرض أو تصويرها بالكاميرا
- تحديد متعدد للسجلات (checkbox)
- تصدير صورة واحدة كـ PDF
- تصدير عدة سجلات محددة في ملف PDF واحد
- (لا توجد طباعة مباشرة على أندرويد) -> تصدير PDF ثم فتحه بتطبيق آخر للطباعة
"""

import io
import os
import sqlite3
import threading

from kivy.metrics import dp
from kivy.utils import platform
from kivy.uix.image import AsyncImage
from kivy.clock import Clock
from kivy.core.window import Window

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton, MDIconButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.list import OneLineAvatarIconListItem, IconLeftWidget
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.label import MDLabel

from PIL import Image as PILImage

APP_DATA_DIR = None  # سيُحدد عند تشغيل التطبيق حسب نظام التشغيل
DB_NAME = "registry_embedded_data.db"


def get_storage_path():
    """تحديد مسار تخزين بيانات التطبيق (متوافق مع أندرويد وسطح المكتب)."""
    if platform == "android":
        from android.storage import app_storage_path  # noqa
        path = app_storage_path()
    else:
        path = os.path.join(os.path.expanduser("~"), ".registry_app")
    os.makedirs(path, exist_ok=True)
    return path


class Database:
    """طبقة الوصول لقاعدة البيانات SQLite (نفس بنية النسخة الأصلية)."""

    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                registry_num TEXT NOT NULL,
                image_data BLOB
            )
            """
        )
        self.conn.commit()

    def add_record(self, name, num, image_bytes):
        self.cursor.execute(
            "INSERT INTO records (name, registry_num, image_data) VALUES (?, ?, ?)",
            (name, num, image_bytes),
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def update_record(self, record_id, name, num, image_bytes=None):
        if image_bytes:
            self.cursor.execute(
                "UPDATE records SET name=?, registry_num=?, image_data=? WHERE id=?",
                (name, num, image_bytes, record_id),
            )
        else:
            self.cursor.execute(
                "UPDATE records SET name=?, registry_num=? WHERE id=?",
                (name, num, record_id),
            )
        self.conn.commit()

    def delete_record(self, record_id):
        self.cursor.execute("DELETE FROM records WHERE id=?", (record_id,))
        self.conn.commit()

    def get_all(self, search_query=""):
        if search_query:
            self.cursor.execute(
                "SELECT id, registry_num, name FROM records "
                "WHERE name LIKE ? OR registry_num LIKE ? ORDER BY id DESC",
                (f"%{search_query}%", f"%{search_query}%"),
            )
        else:
            self.cursor.execute(
                "SELECT id, registry_num, name FROM records ORDER BY id DESC"
            )
        return self.cursor.fetchall()

    def get_record(self, record_id):
        self.cursor.execute(
            "SELECT name, registry_num, image_data FROM records WHERE id=?",
            (record_id,),
        )
        return self.cursor.fetchone()

    def get_image(self, record_id):
        self.cursor.execute(
            "SELECT image_data FROM records WHERE id=?", (record_id,)
        )
        row = self.cursor.fetchone()
        return row[0] if row else None


# ---------------------------------------------------------------------------
# عنصر السجل في القائمة (مع checkbox للتحديد المتعدد)
# ---------------------------------------------------------------------------
class RecordListItem(OneLineAvatarIconListItem):
    def __init__(self, record_id, num, name, on_select, on_checkbox, **kwargs):
        super().__init__(**kwargs)
        self.record_id = record_id
        self.text = f"{name}   |   رقم القيد: {num}"
        self.on_select_callback = on_select

        icon = IconLeftWidget(icon="file-document-outline")
        self.add_widget(icon)

        self.checkbox = MDCheckbox(
            size_hint=(None, None),
            size=(dp(36), dp(36)),
            pos_hint={"center_y": 0.5},
        )
        self.checkbox.bind(
            active=lambda instance, value: on_checkbox(record_id, value)
        )
        self.add_widget(self.checkbox)

    def on_release(self):
        self.on_select_callback(self.record_id)


# ---------------------------------------------------------------------------
# الشاشة الرئيسية
# ---------------------------------------------------------------------------
class MainScreen(MDScreen):
    pass


class RegistryApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db = None
        self.current_record_id = None
        self.selected_image_path = None  # مسار مؤقت للصورة المختارة قبل الحفظ
        self.checked_ids = set()
        self.file_manager = None
        self._dialog = None

    # ----------------------- إعداد التطبيق -----------------------
    def build(self):
        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.theme_style = "Light"
        Window.softinput_mode = "below_target"

        storage_path = get_storage_path()
        db_path = os.path.join(storage_path, DB_NAME)
        self.db = Database(db_path)
        self.storage_path = storage_path

        self.screen = MainScreen()
        self.build_ui()
        self.refresh_list()
        return self.screen

    def build_ui(self):
        root = MDBoxLayout(orientation="vertical")

        # ---------- شريط علوي ----------
        from kivymd.uix.toolbar import MDTopAppBar
        toolbar = MDTopAppBar(title="أرشفة سجلات القيد")
        toolbar.right_action_items = [["magnify", lambda x: self.toggle_search()]]
        root.add_widget(toolbar)

        # ---------- حقل البحث (مخفي ابتدائياً) ----------
        self.search_box = MDBoxLayout(
            size_hint_y=None, height=0, opacity=0, padding=(dp(10), 0)
        )
        self.search_field = MDTextField(
            hint_text="ابحث بالاسم أو رقم القيد",
            mode="rectangle",
        )
        self.search_field.bind(text=lambda inst, val: self.on_search(val))
        self.search_box.add_widget(self.search_field)
        root.add_widget(self.search_box)

        # ---------- منطقة قابلة للتمرير: نموذج الإدخال ----------
        from kivymd.uix.scrollview import MDScrollView

        form_card = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(280),
            padding=dp(15),
            spacing=dp(10),
        )

        self.name_field = MDTextField(hint_text="اسم صاحب القيد", mode="rectangle")
        self.num_field = MDTextField(hint_text="رقم القيد", mode="rectangle")

        form_card.add_widget(self.name_field)
        form_card.add_widget(self.num_field)

        img_row = MDBoxLayout(spacing=dp(10), size_hint_y=None, height=dp(48))
        btn_camera = MDRaisedButton(
            text="تصوير 📷", on_release=lambda x: self.choose_image("camera")
        )
        btn_gallery = MDRaisedButton(
            text="من المعرض 🖼️", on_release=lambda x: self.choose_image("gallery")
        )
        img_row.add_widget(btn_camera)
        img_row.add_widget(btn_gallery)
        form_card.add_widget(img_row)

        self.img_status_label = MDLabel(
            text="لم يتم اختيار صورة بعد",
            theme_text_color="Error",
            size_hint_y=None,
            height=dp(24),
            halign="right",
        )
        form_card.add_widget(self.img_status_label)

        btn_row = MDBoxLayout(spacing=dp(10), size_hint_y=None, height=dp(48))
        btn_row.add_widget(
            MDRaisedButton(
                text="إضافة",
                md_bg_color=(0.3, 0.69, 0.31, 1),
                on_release=lambda x: self.add_record(),
            )
        )
        btn_row.add_widget(
            MDRaisedButton(
                text="تعديل",
                md_bg_color=(0.13, 0.59, 0.95, 1),
                on_release=lambda x: self.update_record(),
            )
        )
        btn_row.add_widget(
            MDRaisedButton(
                text="حذف",
                md_bg_color=(0.96, 0.26, 0.21, 1),
                on_release=lambda x: self.confirm_delete(),
            )
        )
        form_card.add_widget(btn_row)

        btn_row2 = MDBoxLayout(spacing=dp(10), size_hint_y=None, height=dp(48))
        btn_row2.add_widget(
            MDRaisedButton(text="تفريغ الخانات", on_release=lambda x: self.clear_inputs())
        )
        btn_row2.add_widget(
            MDRaisedButton(
                text="عرض الصورة 🔍",
                on_release=lambda x: self.show_image_preview(),
            )
        )
        form_card.add_widget(btn_row2)

        root.add_widget(form_card)

        # ---------- أزرار التحديد والتصدير الجماعي ----------
        export_row = MDBoxLayout(
            spacing=dp(10), size_hint_y=None, height=dp(48), padding=(dp(10), 0)
        )
        export_row.add_widget(
            MDRaisedButton(text="تحديد الكل ☑", on_release=lambda x: self.check_all())
        )
        export_row.add_widget(
            MDRaisedButton(text="إلغاء التحديد ☐", on_release=lambda x: self.uncheck_all())
        )
        root.add_widget(export_row)

        root.add_widget(
            MDRaisedButton(
                text="تصدير السجلات المحددة كملف PDF واحد 📚",
                size_hint_x=1,
                md_bg_color=(0.4, 0.23, 0.72, 1),
                on_release=lambda x: self.export_multiple_to_pdf(),
            )
        )

        export_single_row = MDBoxLayout(
            spacing=dp(10), size_hint_y=None, height=dp(48), padding=(dp(10), dp(5))
        )
        export_single_row.add_widget(
            MDRaisedButton(
                text="تصدير الصورة الحالية PDF 📄",
                md_bg_color=(0, 0.59, 0.53, 1),
                on_release=lambda x: self.export_single_to_pdf(),
            )
        )
        root.add_widget(export_single_row)

        # ---------- قائمة السجلات ----------
        from kivymd.uix.list import MDList

        scroll = MDScrollView()
        self.record_list = MDList()
        scroll.add_widget(self.record_list)
        root.add_widget(scroll)

        self.screen.add_widget(root)

    # ----------------------- البحث -----------------------
    def toggle_search(self):
        if self.search_box.height == 0:
            self.search_box.height = dp(56)
            self.search_box.opacity = 1
        else:
            self.search_box.height = 0
            self.search_box.opacity = 0
            self.search_field.text = ""

    def on_search(self, text):
        self.refresh_list(text)

    # ----------------------- تحميل القائمة -----------------------
    def refresh_list(self, search_query=""):
        self.record_list.clear_widgets()
        rows = self.db.get_all(search_query)
        for record_id, num, name in rows:
            item = RecordListItem(
                record_id=record_id,
                num=num,
                name=name,
                on_select=self.select_record,
                on_checkbox=self.on_checkbox_toggle,
            )
            if record_id in self.checked_ids:
                item.checkbox.active = True
            self.record_list.add_widget(item)

    def on_checkbox_toggle(self, record_id, active):
        if active:
            self.checked_ids.add(record_id)
        else:
            self.checked_ids.discard(record_id)

    def check_all(self):
        for item in self.record_list.children:
            if isinstance(item, RecordListItem):
                item.checkbox.active = True
                self.checked_ids.add(item.record_id)

    def uncheck_all(self):
        for item in self.record_list.children:
            if isinstance(item, RecordListItem):
                item.checkbox.active = False
        self.checked_ids.clear()

    # ----------------------- اختيار / تحديد سجل -----------------------
    def select_record(self, record_id):
        self.current_record_id = record_id
        name, num, img_bytes = self.db.get_record(record_id)
        self.name_field.text = name
        self.num_field.text = num
        self.selected_image_path = None
        if img_bytes:
            self.img_status_label.text = "هذا السجل يحتوي على صورة محفوظة"
            self.img_status_label.theme_text_color = "Custom"
            self.img_status_label.text_color = (0.2, 0.6, 0.2, 1)
        else:
            self.img_status_label.text = "لا توجد صورة لهذا السجل"
            self.img_status_label.theme_text_color = "Error"

    # ----------------------- اختيار صورة (كاميرا / معرض) -----------------------
    def choose_image(self, source):
        """
        على أندرويد: نستخدم plyer لاختيار صورة من المعرض أو تصويرها بالكاميرا.
        على سطح المكتب (أثناء الاختبار بـ python main.py): نفتح متصفح ملفات Kivy.
        """
        if platform == "android":
            self._android_pick_image(source)
        else:
            self._desktop_pick_image()

    def _android_pick_image(self, source):
        try:
            from plyer import camera, filechooser

            if source == "camera":
                storage_path = self.storage_path
                tmp_path = os.path.join(storage_path, "tmp_capture.jpg")
                camera.take_picture(
                    filename=tmp_path,
                    on_complete=lambda path: self._on_image_picked(path or tmp_path),
                )
            else:
                filechooser.open_file(
                    on_selection=self._on_filechooser_result,
                    filters=["*.jpg", "*.jpeg", "*.png"],
                )
        except Exception as e:
            self.show_snackbar(f"تعذر فتح الكاميرا/المعرض: {e}")

    def _on_filechooser_result(self, selection):
        if selection:
            self._on_image_picked(selection[0])

    def _on_image_picked(self, path):
        if path and os.path.exists(path):
            self.selected_image_path = path
            self.img_status_label.text = f"تم تجهيز: {os.path.basename(path)}"
            self.img_status_label.theme_text_color = "Custom"
            self.img_status_label.text_color = (0.2, 0.6, 0.2, 1)
        else:
            self.show_snackbar("لم يتم اختيار صورة")

    def _desktop_pick_image(self):
        """بديل لاختبار التطبيق على الحاسوب قبل تصديره لـ APK."""
        from kivymd.uix.filemanager import MDFileManager

        if not self.file_manager:
            self.file_manager = MDFileManager(
                exit_manager=lambda *a: self.file_manager.close(),
                select_path=self._on_desktop_path_selected,
                ext=[".jpg", ".jpeg", ".png"],
            )
        self.file_manager.show(os.path.expanduser("~"))

    def _on_desktop_path_selected(self, path):
        self.file_manager.close()
        self._on_image_picked(path)

    def _read_image_bytes(self):
        if self.selected_image_path and os.path.exists(self.selected_image_path):
            with open(self.selected_image_path, "rb") as f:
                return f.read()
        return None

    def show_image_preview(self):
        img_bytes = None
        if self.selected_image_path:
            img_bytes = self._read_image_bytes()
        elif self.current_record_id:
            img_bytes = self.db.get_image(self.current_record_id)

        if not img_bytes:
            self.show_snackbar("لا توجد صورة لعرضها")
            return

        tmp_preview = os.path.join(self.storage_path, "preview_tmp.png")
        try:
            PILImage.open(io.BytesIO(img_bytes)).save(tmp_preview)
        except Exception as e:
            self.show_snackbar(f"خطأ في قراءة الصورة: {e}")
            return

        box = MDBoxLayout(orientation="vertical", size_hint_y=None, height=dp(400))
        img_widget = AsyncImage(source=tmp_preview, allow_stretch=True, keep_ratio=True)
        box.add_widget(img_widget)

        self._dialog = MDDialog(
            title="معاينة صفحة القيد",
            type="custom",
            content_cls=box,
            buttons=[
                MDFlatButton(text="إغلاق", on_release=lambda x: self._dialog.dismiss())
            ],
        )
        self._dialog.open()

    # ----------------------- عمليات CRUD -----------------------
    def add_record(self):
        name = self.name_field.text.strip()
        num = self.num_field.text.strip()
        if not name or not num:
            self.show_snackbar("الرجاء كتابة الاسم ورقم القيد!")
            return
        img_bytes = self._read_image_bytes()
        self.db.add_record(name, num, img_bytes)
        self.show_snackbar("تم حفظ السجل بنجاح")
        self.refresh_list(self.search_field.text)
        self.clear_inputs()

    def update_record(self):
        if not self.current_record_id:
            self.show_snackbar("اختر سجلاً لتعديله")
            return
        name = self.name_field.text.strip()
        num = self.num_field.text.strip()
        img_bytes = self._read_image_bytes()
        self.db.update_record(self.current_record_id, name, num, img_bytes)
        self.show_snackbar("تم التعديل بنجاح")
        self.refresh_list(self.search_field.text)
        self.clear_inputs()

    def confirm_delete(self):
        if not self.current_record_id:
            self.show_snackbar("اختر سجلاً لحذفه")
            return
        self._dialog = MDDialog(
            title="تأكيد الحذف",
            text="هل أنت متأكد من حذف هذا السجل؟",
            buttons=[
                MDFlatButton(text="إلغاء", on_release=lambda x: self._dialog.dismiss()),
                MDFlatButton(
                    text="حذف",
                    theme_text_color="Custom",
                    text_color=(1, 0, 0, 1),
                    on_release=lambda x: self._do_delete(),
                ),
            ],
        )
        self._dialog.open()

    def _do_delete(self):
        self._dialog.dismiss()
        self.db.delete_record(self.current_record_id)
        self.checked_ids.discard(self.current_record_id)
        self.clear_inputs()
        self.refresh_list(self.search_field.text)

    def clear_inputs(self):
        self.name_field.text = ""
        self.num_field.text = ""
        self.selected_image_path = None
        self.current_record_id = None
        self.img_status_label.text = "لم يتم اختيار صورة بعد"
        self.img_status_label.theme_text_color = "Error"

    # ----------------------- التصدير إلى PDF -----------------------
    def export_single_to_pdf(self):
        if not self.current_record_id:
            self.show_snackbar("الرجاء اختيار سجل أولاً لتصديره كـ PDF")
            return
        name, num, img_bytes = self.db.get_record(self.current_record_id)
        if not img_bytes:
            self.show_snackbar("لا توجد صورة لتصديرها لهذا السجل")
            return

        out_dir = self._get_export_dir()
        safe_name = f"{num}_{name}".replace("/", "_").replace("\\", "_")
        file_path = os.path.join(out_dir, f"{safe_name}.pdf")

        try:
            img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
            img.save(file_path, "PDF")
            self.show_snackbar(f"تم الحفظ في: {file_path}")
            self._offer_open_pdf(file_path)
        except Exception as e:
            self.show_snackbar(f"فشل تصدير الـ PDF: {e}")

    def export_multiple_to_pdf(self):
        if not self.checked_ids:
            self.show_snackbar("الرجاء تحديد (☑) السجلات المراد تصديرها أولاً")
            return

        pdf_images = []
        for record_id in self.checked_ids:
            img_bytes = self.db.get_image(record_id)
            if img_bytes:
                try:
                    img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
                    pdf_images.append(img)
                except Exception:
                    continue

        if not pdf_images:
            self.show_snackbar("السجلات المحددة لا تحتوي على صور!")
            return

        out_dir = self._get_export_dir()
        file_path = os.path.join(out_dir, "نسخة_احتياطية_مجمعة.pdf")

        try:
            first_image = pdf_images[0]
            remaining_images = pdf_images[1:]
            first_image.save(
                file_path, "PDF", save_all=True, append_images=remaining_images
            )
            self.show_snackbar(f"تم تصدير ({len(pdf_images)}) صفحة بنجاح")
            self.uncheck_all()
            self.refresh_list(self.search_field.text)
            self._offer_open_pdf(file_path)
        except Exception as e:
            self.show_snackbar(f"فشلت عملية التصدير الجماعي: {e}")

    def _get_export_dir(self):
        """مجلد التصدير: Downloads على أندرويد، أو مجلد المنزل على الحاسوب."""
        if platform == "android":
            from android.storage import primary_external_storage_path  # noqa

            base = primary_external_storage_path()
            out_dir = os.path.join(base, "Download", "RegistryExports")
        else:
            out_dir = os.path.join(os.path.expanduser("~"), "RegistryExports")
        os.makedirs(out_dir, exist_ok=True)
        return out_dir

    def _offer_open_pdf(self, file_path):
        """
        محاولة فتح/مشاركة ملف PDF بعد التصدير (لا توجد طباعة مباشرة على أندرويد،
        المستخدم يفتح الملف من تطبيق آخر يدعم الطباعة مثل Google Drive أو أي قارئ PDF).
        نستخدم plyer.share الذي يعتمد داخلياً على FileProvider بشكل آمن وجاهز.
        """
        if platform != "android":
            return
        try:
            from plyer import share

            share.share(
                title="فتح / مشاركة ملف PDF",
                filepath=file_path,
                mimetype="application/pdf",
            )
        except Exception as e:
            self.show_snackbar(
                f"تم الحفظ في مجلد Download/RegistryExports. "
                f"(لم تتمكن المشاركة التلقائية من العمل: {e})"
            )

    # ----------------------- مساعدات عامة -----------------------
    def show_snackbar(self, message):
        Snackbar(text=message, duration=2.5).open()


if __name__ == "__main__":
    RegistryApp().run()
