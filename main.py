# -*- coding: utf-8 -*-
"""
taqaddum_appointments.py — PySide6

- الدخول:
    - يقبل الحساب الافتراضي: المستخدم "مصطفى" — الرمز "1234"
    - و/أو أي مستخدم تُنشئه في قسم "المستخدمون" (جدول users في SQLite).
- صور بجانب الملف: 1 (خلفية)، 2 (صورة الدكتور)، 3 (الشعار) بأي امتداد png/jpg/jpeg
- واجهة زجاجية + خلفية مضمونة الظهور
- SQLite: appointments.db
- بحث حي + فلاتر: الكل/اليوم/المتأخرة/المنجزة
- تذكير أيام/ساعات/دقائق + نافذة تنبيه (تم/تأجيل)
- تصدير:
   (1) بطاقة معايدة كبيرة لشخص واحد — العنوان بالوسط، الدكتور يسار، الشعار يمين،
       التفاصيل من اليسار مع Badges بيضاء خلف النص لمنع اختفاء الكتابة.
   (2) بطاقة قائمة للكل (حسب العرض الحالي).
- قسم "👤 المستخدمون": إضافة/حذف مستخدمين دخول (تخزين نصّي بسيط).
"""

import os, sys, sqlite3, datetime, html
from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QDateTime, QTimer
from PySide6.QtGui import QIcon, QPixmap, QAction, QPainter, QFont, QTextOption
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog, QLabel, QLineEdit, QTextEdit,
    QDateTimeEdit, QSpinBox, QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout,
    QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog, QFrame, QComboBox,
    QGraphicsDropShadowEffect, QRadioButton, QButtonGroup
)

APP_NAME = "نظام مواعيد — حزب تقدم"
DB_NAME  = "appointments.db"

# ===================== مساعدات الصور والخلفية =====================
def _candidate_dirs() -> List[str]:
    ds: List[str] = []
    try:
        ds.append(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pass
    ds.append(os.getcwd())
    base = getattr(sys, "_MEIPASS", None)
    if base:
        ds.append(base)
    out, seen = [], set()
    for d in ds:
        if d and d not in seen:
            out.append(d); seen.add(d)
    return out

def _candidate_names(stem: str) -> List[str]:
    stem0, ext = os.path.splitext(stem)
    exts = [".png",".jpg",".jpeg",".PNG",".JPG",".JPEG"]
    return [os.path.basename(stem)] if ext in exts else [stem0+e for e in exts]

def find_image(stem: str) -> Optional[str]:
    for d in _candidate_dirs():
        for n in _candidate_names(stem):
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None

def apply_background(widget: QWidget, stem: str = "1"):
    """يطبّق الخلفية مباشرة على الـWidget بأسلوب مضمون."""
    if not widget.objectName():
        widget.setObjectName(widget.__class__.__name__)
    img = find_image(stem)
    if img:
        img = img.replace("\\", "/")
        css = f'#{widget.objectName()}{{border-image:url("{img}") 0 0 0 0 stretch stretch; background:transparent;}}'
    else:
        css = f'#{widget.objectName()}{{background:#0f0f0f;}}'
    widget.setStyleSheet(widget.styleSheet() + "\n" + css)

# ===================== قاعدة البيانات (مع ترقية تلقائية) =====================
def _table_columns(cur, table: str) -> List[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]  # r[1] = name

def _add_column_if_missing(cur, table: str, col_def: str, col_name: str):
    cols = _table_columns(cur, table)
    if col_name not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")

def ensure_db():
    con = sqlite3.connect(DB_NAME); cur = con.cursor()

    # جدول المواعيد
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person TEXT NOT NULL,
            phone TEXT,
            address TEXT,
            notes TEXT,
            companions TEXT,
            appt_dt TEXT NOT NULL,             -- ISO
            remind_amount INTEGER DEFAULT 1,
            remind_unit TEXT DEFAULT 'days',   -- days|hours|minutes
            notified INTEGER DEFAULT 0,
            snooze_until TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_appt_dt ON appointments(appt_dt)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_person ON appointments(person)")

    # جدول المستخدمين (إنشاء مبدئي بسيط ثم ترقية للأعمدة الناقصة)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL
        )
    """)
    # تأكد من الأعمدة
    _add_column_if_missing(cur, "users", "password TEXT", "password")
    _add_column_if_missing(cur, "users", "created_at TEXT DEFAULT CURRENT_TIMESTAMP", "created_at")

    # حساب افتراضي
    cur.execute("SELECT 1 FROM users WHERE username=?", ("مصطفى",))
    if cur.fetchone():
        # حدّث كلمة المرور الافتراضية إذا كانت NULL/فارغة
        cur.execute("""
            UPDATE users SET password=COALESCE(NULLIF(password,''), '1234')
            WHERE username=?
        """, ("مصطفى",))
    else:
        cur.execute("INSERT OR IGNORE INTO users(username,password) VALUES(?,?)", ("مصطفى","1234"))

    con.commit(); con.close()

def db_q(q, a=()):
    con = sqlite3.connect(DB_NAME); cur = con.cursor()
    cur.execute(q, a); rows = cur.fetchall(); con.close(); return rows

def db_x(q, a=()):
    con = sqlite3.connect(DB_NAME); cur = con.cursor()
    cur.execute(q, a); con.commit(); con.close()

# ===================== حوار الدخول =====================
class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setObjectName("LoginDialog")
        self.setWindowTitle("تسجيل الدخول")
        self.setMinimumWidth(420)
        v = QVBoxLayout(self); v.setContentsMargins(18,18,18,18); v.setSpacing(10)

        t = QLabel("نظام مواعيد المكتب الإعلامي —  الاستاذ عمر مصطفى العرسان")
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-weight:800;color:#FFA033;font-size:17px;")
        v.addWidget(t)

        self.user = QLineEdit("مصطفى")
        self.pwd  = QLineEdit("1234"); self.pwd.setEchoMode(QLineEdit.Password)
        v.addWidget(self.user); v.addWidget(self.pwd)

        go = QPushButton("دخول"); go.clicked.connect(self.try_login)
        v.addWidget(go, alignment=Qt.AlignLeft)

        self.setStyleSheet("""
        QLineEdit{color:#fff;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.22);border-radius:12px;padding:9px;}
        QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ff9b3e, stop:1 #ff7a12);
                    color:#151515;border:none;border-radius:12px;padding:10px 18px;font-weight:800;}
        QLabel{color:#eee;}
        """)
        apply_background(self, "1")

    def try_login(self):
        u = self.user.text().strip()
        p = self.pwd.text()
        ok = False
        try:
            con = sqlite3.connect(DB_NAME); cur = con.cursor()
            cur.execute("SELECT 1 FROM users WHERE username=? AND password=?", (u, p))
            ok = cur.fetchone() is not None
            con.close()
        except Exception:
            ok = False

        # القبول أيضًا بالحساب الافتراضي
        if ok or (u == "مصطفى" and p == "1234"):
            self.accept()
        else:
            # ✅ تنبيه عام
            QMessageBox.warning(self, "خطأ", "تحقق من اسم المستخدم وكلمة المرور.")

# ===================== حوار إدارة المستخدمين =====================
class UsersDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UsersDialog")
        self.setWindowTitle("إدارة المستخدمين")
        self.setMinimumSize(560, 420)

        root = QVBoxLayout(self); root.setContentsMargins(16,16,16,16); root.setSpacing(10)

        # نموذج إضافة
        form = QHBoxLayout()
        self.e_user = QLineEdit(); self.e_user.setPlaceholderText("اسم المستخدم")
        self.e_pass = QLineEdit(); self.e_pass.setPlaceholderText("كلمة المرور"); self.e_pass.setEchoMode(QLineEdit.Password)
        self.btn_add = QPushButton("إضافة"); self.btn_add.clicked.connect(self.add_user)
        form.addWidget(self.e_user); form.addWidget(self.e_pass); form.addWidget(self.btn_add)
        root.addLayout(form)

        # جدول المستخدمين
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["#", "المستخدم", "تاريخ الإنشاء"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        # أزرار أسفل
        bottom = QHBoxLayout()
        self.btn_del = QPushButton("حذف المحدد"); self.btn_del.clicked.connect(self.delete_selected)
        close_btn = QPushButton("إغلاق"); close_btn.clicked.connect(self.accept)
        bottom.addWidget(self.btn_del); bottom.addStretch(1); bottom.addWidget(close_btn)
        root.addLayout(bottom)

        # نمط وخلفية
        self.setStyleSheet("""
        QLineEdit, QTableWidget{
            color:#fff;background: rgba(255,255,255,.10);
            border:1px solid rgba(255,255,255,.22); border-radius:12px; padding:8px 10px;
        }
        QPushButton{
            background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ff9b3e, stop:1 #ff7a12);
            color:#151515; border:none; border-radius:12px; padding:8px 16px; font-weight:900;
        }
        QLabel{color:#f0f0f0;}
        QHeaderView::section{ background: rgba(255,160,51,.18); color:#ffd6a4; padding:7px; border:none; }
        """)
        apply_background(self, "1")

        self.refresh()

    def refresh(self):
        rows = db_q("SELECT id, username, created_at FROM users ORDER BY id ASC")
        self.table.setRowCount(0)
        for _id, uname, created in rows:
            r = self.table.rowCount(); self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(_id)))
            self.table.setItem(r, 1, QTableWidgetItem(uname))
            self.table.setItem(r, 2, QTableWidgetItem(created or ""))
            self.table.item(r,0).setTextAlignment(Qt.AlignCenter)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def add_user(self):
        u = (self.e_user.text() or "").strip()
        p = self.e_pass.text()
        if not u or not p:
            return QMessageBox.information(self, "تنبيه", "يرجى إدخال اسم المستخدم وكلمة المرور.")
        try:
            db_x("INSERT INTO users(username,password) VALUES(?,?)", (u, p))
            self.e_user.clear(); self.e_pass.clear()
            self.refresh()
            QMessageBox.information(self, "نجاح", "تمت إضافة المستخدم.")
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "موجود", "اسم المستخدم مسجَّل مسبقًا.")
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"تعذر الإضافة:\n{e}")

    def delete_selected(self):
        r = self.table.currentRow()
        if r < 0:
            return QMessageBox.information(self, "حذف", "اختر مستخدمًا من الجدول.")
        _id = int(self.table.item(r, 0).text())
        uname = self.table.item(r, 1).text()
        if QMessageBox.question(self, "تأكيد", f"حذف المستخدم «{uname}»؟")==QMessageBox.Yes:
            try:
                db_x("DELETE FROM users WHERE id=?", (_id,))
                self.refresh()
                QMessageBox.information(self, "تم", "تم حذف المستخدم.")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الحذف:\n{e}")

# ===================== أدوات رسم للبطاقات =====================
def draw_badge(p: QPainter, rect: QtCore.QRect, radius: int = 14):
    p.save()
    p.setPen(QtGui.QPen(QtGui.QColor(0,0,0,25), 2))
    p.setBrush(QtGui.QColor(255,255,255,245))
    p.drawRoundedRect(rect, radius, radius)
    p.restore()

def draw_wrapped_text(p: QPainter, rect: QtCore.QRect, text: str, font: QFont,
                      color: QtGui.QColor, align: Qt.AlignmentFlag = Qt.AlignLeft | Qt.AlignTop,
                      rtl: bool = True) -> float:
    doc = QtGui.QTextDocument()
    opt = QTextOption()
    opt.setWrapMode(QTextOption.WordWrap)
    opt.setAlignment(align)
    if rtl:
        opt.setTextDirection(Qt.RightToLeft)
    doc.setDefaultTextOption(opt)
    doc.setDefaultFont(font)
    safe = html.escape(text or "")
    doc.setHtml(f'<div style="color:#111; white-space:pre-wrap;">{safe}</div>')
    doc.setTextWidth(rect.width())
    p.save()
    p.translate(rect.topLeft())
    doc.drawContents(p, QtCore.QRectF(0, 0, rect.width(), rect.height()))
    p.restore()
    return float(doc.size().height())

def draw_center_title(p: QPainter, rect: QtCore.QRect, text: str):
    p.save()
    font = QFont("Cairo", 40, QFont.Black)
    p.setFont(font)
    p.setPen(QtGui.QColor(0,0,0,70))
    p.drawText(rect.adjusted(2,2,2,2), Qt.AlignCenter, text)
    p.setPen(QtGui.QColor("#141414"))
    p.drawText(rect, Qt.AlignCenter, text)
    p.restore()

# ===================== النافذة الرئيسية =====================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setObjectName("MainWindow")
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1220, 740)
        self.setWindowIcon(QIcon(find_image("3") or ""))

        self._build_ui()
        self.refresh()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_reminders)
        self.timer.start(60*1000)

    def _css(self) -> str:
        return """
        #Card{ background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.18); border-radius:18px; }
        QLabel#TitleBig{color:#FFA033;font-size:22px;font-weight:900;}
        QLabel#TitleSmall{color:#ffd6a4;font-size:13px;}
        QLabel{color:#f0f0f0;}
        QLineEdit, QTextEdit, QDateTimeEdit, QSpinBox, QComboBox{
            color:#fff;background: rgba(255,255,255,.10);
            border:1px solid rgba(255,255,255,.22); border-radius:12px; padding:8px 10px; selection-background-color:#ff8c3a;
        }
        QPushButton{
            background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ff9b3e, stop:1 #ff7a12);
            color:#151515; border:none; border-radius:12px; padding:9px 16px; font-weight:900;
        }
        QTableWidget{
            background: rgba(0,0,0,.38); color:#f2f2f2;
            border:1px solid rgba(255,255,255,.14); border-radius:12px; gridline-color:rgba(255,255,255,.15);
        }
        QHeaderView::section{ background: rgba(255,160,51,.18); color:#ffd6a4; padding:7px; border:none; }
        QStatusBar{ color:#ddd; }
        """

    def _build_ui(self):
        QApplication.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet(self._css())
        apply_background(self, "1")

        root = QWidget(objectName="Central")
        self.setCentralWidget(root)
        apply_background(root, "1")
        main = QVBoxLayout(root); main.setContentsMargins(12,12,12,12); main.setSpacing(10)

        # Header
        header = QFrame(objectName="Card"); H = QHBoxLayout(header); H.setContentsMargins(16,16,16,16); H.setSpacing(12)

        logo = QLabel()
        if (p3:=find_image("3")):
            logo.setPixmap(QPixmap(p3).scaledToHeight(86, Qt.SmoothTransformation))
        else:
            logo.setText("3 غير موجود"); logo.setStyleSheet("color:#FFA033;")
        H.addWidget(logo, 0, Qt.AlignRight|Qt.AlignVCenter)

        titles = QVBoxLayout()
        t1 = QLabel("نظام مواعيد المكتب الإعلامي — الاستاذ عمر مصطفى العرسان "); t1.setObjectName("TitleBig")
        t2 = QLabel("الاستاذ عمر مصطفى العرسان"); t2.setObjectName("TitleSmall")
        titles.addWidget(t1); titles.addWidget(t2)
        H.addLayout(titles, 1)

        dr = QLabel()
        if (p2:=find_image("2")):
            pm = QPixmap(p2).scaled(120,120, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            dr.setPixmap(pm); dr.setFixedSize(120,120); dr.setStyleSheet("border-radius:14px;")
            glow = QGraphicsDropShadowEffect(self); glow.setBlurRadius(52); glow.setOffset(0,0); glow.setColor(QtGui.QColor("#ff9b3e"))
            dr.setGraphicsEffect(glow)
        else:
            dr.setText("2 غير موجود"); dr.setStyleSheet("color:#FFA033;")
        H.addWidget(dr, 0, Qt.AlignLeft|Qt.AlignVCenter)

        main.addWidget(header)

        # Top buttons
        top = QHBoxLayout()
        self.btn_all=QPushButton("الكل"); self.btn_all.clicked.connect(lambda:self.set_mode("all"))
        self.btn_today=QPushButton("اليوم"); self.btn_today.clicked.connect(lambda:self.set_mode("today"))
        self.btn_late=QPushButton("المتأخرة"); self.btn_late.clicked.connect(lambda:self.set_mode("late"))
        self.btn_done=QPushButton("المُنجزة"); self.btn_done.clicked.connect(lambda:self.set_mode("done"))
        self.btn_mark=QPushButton("علِّم كمُنجز"); self.btn_mark.clicked.connect(self.mark_done)
        self.btn_export=QPushButton("تصدير بطاقة"); self.btn_export.clicked.connect(self.export_card)
        self.btn_report=QPushButton("تقرير اليوم (PNG)"); self.btn_report.clicked.connect(self.export_today_report)
        self.btn_users=QPushButton("👤 المستخدمون"); self.btn_users.clicked.connect(self.open_users)

        for b in [self.btn_all,self.btn_today,self.btn_late,self.btn_done]:
            top.addWidget(b)
        top.addSpacing(10); top.addWidget(self.btn_mark)
        top.addStretch(1)
        top.addWidget(self.btn_export); top.addWidget(self.btn_report); top.addWidget(self.btn_users)
        main.addLayout(top)

        # Body
        body = QHBoxLayout(); body.setSpacing(12); main.addLayout(body, 1)

        form_card = QFrame(objectName="Card"); F = QGridLayout(form_card); F.setContentsMargins(16,16,16,16); F.setSpacing(8)
        self.e_person = QLineEdit(); self.e_person.setPlaceholderText("الاسم الثلاثي")
        self.e_phone  = QLineEdit(); self.e_phone.setPlaceholderText("الهاتف")
        self.e_addr   = QLineEdit(); self.e_addr.setPlaceholderText("السكن")
        self.e_dt     = QDateTimeEdit(QDateTime.currentDateTime()); self.e_dt.setDisplayFormat("dd/MM/yyyy hh:mm AP"); self.e_dt.setCalendarPopup(True)
        self.e_notes  = QTextEdit(); self.e_notes.setPlaceholderText("ملاحظات")
        self.e_comp   = QTextEdit(); self.e_comp.setPlaceholderText("المرافقون (افصل بفواصل ,)")
        self.e_amt    = QSpinBox(); self.e_amt.setRange(1,365*3); self.e_amt.setValue(1)
        self.e_unit   = QComboBox(); self.e_unit.addItems(["أيام","ساعات","دقائق"])
        F.addWidget(QLabel("الاسم:"),0,0); F.addWidget(self.e_person,0,1,1,3)
        F.addWidget(QLabel("الهاتف:"),1,0); F.addWidget(self.e_phone,1,1)
        F.addWidget(QLabel("السكن:"),1,2); F.addWidget(self.e_addr,1,3)
        F.addWidget(QLabel("الموعد:"),2,0); F.addWidget(self.e_dt,2,1)
        F.addWidget(QLabel("التذكير:"),2,2); rr=QHBoxLayout(); rr.addWidget(self.e_amt); rr.addWidget(self.e_unit); F.addLayout(rr,2,3)
        F.addWidget(QLabel("المرافقون:"),3,0); F.addWidget(self.e_comp,3,1,1,3)
        F.addWidget(QLabel("الملاحظات:"),4,0); F.addWidget(self.e_notes,4,1,1,3)
        bb = QHBoxLayout()
        b_new=QPushButton("جديد"); b_new.clicked.connect(self.clear_form)
        b_save=QPushButton("حفظ/تحديث"); b_save.clicked.connect(self.save_record)
        b_del=QPushButton("حذف"); b_del.clicked.connect(self.delete_record)
        bb.addWidget(b_new); bb.addWidget(b_save); bb.addWidget(b_del); bb.addStretch(1)
        F.addLayout(bb,5,0,1,4)
        body.addWidget(form_card,4)

        table_card = QFrame(objectName="Card"); v = QVBoxLayout(table_card); v.setContentsMargins(16,16,16,16); v.setSpacing(8)
        self.e_search = QLineEdit(); self.e_search.setPlaceholderText("بحث: الاسم/الهاتف/السكن/الملاحظات/المرافقون"); self.e_search.textChanged.connect(self.apply_filter)
        v.addWidget(self.e_search)
        self.table = QTableWidget(0,9)
        self.table.setHorizontalHeaderLabels(["#","الاسم","الهاتف","السكن","الموعد","التذكير","المرافقون","ملاحظات","حالة"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.load_selected)
        v.addWidget(self.table,1)
        body.addWidget(table_card,6)

        self.statusBar().showMessage("جاهز.")
        self._mode="all"; self._current_id=None

    def open_users(self):
        dlg = UsersDialog(self)
        dlg.exec()
        self.statusBar().showMessage("تم تحديث قائمة المستخدمين.", 4000)

    # --------------------- بيانات & جدول ---------------------
    def refresh(self):
        self._all = db_q("""SELECT id, person, phone, address, notes, companions,
                                   appt_dt, remind_amount, remind_unit, notified, snooze_until
                            FROM appointments ORDER BY datetime(appt_dt) ASC""")
        self.apply_filter()

    def set_mode(self, mode): self._mode=mode; self.apply_filter()

    def apply_filter(self):
        q = (self.e_search.text() or "").strip().lower()
        now = datetime.datetime.now()
        rows = self._all
        if self._mode=="today":
            rows = [r for r in rows if datetime.datetime.fromisoformat(r[6]).date()==now.date()]
        elif self._mode=="late":
            rows = [r for r in rows if r[9]==0 and not r[10] and datetime.datetime.fromisoformat(r[6])<now]
        elif self._mode=="done":
            rows = [r for r in rows if r[9]==1]
        if q:
            rows = [r for r in rows if q in " ".join([str(x or "") for x in [r[1],r[2],r[3],r[4],r[5]]]).lower()]
        self.fill_table(rows)

    def fill_table(self, rows):
        self.table.setRowCount(0)
        for r in rows:
            _id, person, phone, addr, notes, comp, iso, amt, unit, notified, snooze = r
            dt = datetime.datetime.fromisoformat(iso)
            row = self.table.rowCount(); self.table.insertRow(row)
            items = [
                QTableWidgetItem(str(_id)),
                QTableWidgetItem(person or ""), QTableWidgetItem(phone or ""), QTableWidgetItem(addr or ""),
                QTableWidgetItem(dt.strftime("%d/%m/%Y %I:%M %p")),
                QTableWidgetItem(f"{amt} "+{"days":"يوم/أيام","hours":"ساعة/ساعات","minutes":"دقيقة/دقائق"}[unit]),
                QTableWidgetItem(comp or ""), QTableWidgetItem(notes or ""),
                QTableWidgetItem("تم" if notified else ("مؤجّل" if snooze else ("متأخر" if dt<datetime.datetime.now() else "قادم")))
            ]
            items[0].setTextAlignment(Qt.AlignCenter); items[5].setTextAlignment(Qt.AlignCenter)
            for it in items:
                if notified: it.setForeground(QtGui.QBrush(QtGui.QColor("#a0ffa0")))
            for c,it in enumerate(items): self.table.setItem(row, c, it)
            self.table.item(row,4).setData(Qt.UserRole, iso)
        self.table.resizeColumnsToContents(); self.table.horizontalHeader().setStretchLastSection(True)
        self.statusBar().showMessage(f"عدد السجلات: {len(rows)}")

    def clear_form(self):
        self._current_id=None; self.table.clearSelection()
        self.e_person.clear(); self.e_phone.clear(); self.e_addr.clear()
        self.e_notes.clear(); self.e_comp.clear()
        self.e_dt.setDateTime(QDateTime.currentDateTime()); self.e_amt.setValue(1); self.e_unit.setCurrentIndex(0)

    def load_selected(self):
        r = self.table.currentRow()
        if r<0: return
        self._current_id = int(self.table.item(r,0).text())
        self.e_person.setText(self.table.item(r,1).text())
        self.e_phone.setText(self.table.item(r,2).text())
        self.e_addr.setText(self.table.item(r,3).text())
        self.e_dt.setDateTime(QDateTime.fromString(self.table.item(r,4).data(Qt.UserRole), Qt.ISODate))
        self.e_comp.setPlainText(self.table.item(r,6).text() if self.table.item(r,6) else "")
        self.e_notes.setPlainText(self.table.item(r,7).text() if self.table.item(r,7) else "")

    def save_record(self):
        p = self.e_person.text().strip()
        if not p: return QMessageBox.warning(self,"تنبيه","الاسم مطلوب.")
        phone=self.e_phone.text().strip(); addr=self.e_addr.text().strip()
        notes=self.e_notes.toPlainText().strip(); comp=self.e_comp.toPlainText().strip()
        iso=self.e_dt.dateTime().toPython().isoformat()
        amt=int(self.e_amt.value()); unit={"أيام":"days","ساعات":"hours","دقائق":"minutes"}[self.e_unit.currentText()]
        if self._current_id is None:
            db_x("""INSERT INTO appointments(person,phone,address,notes,companions,appt_dt,remind_amount,remind_unit,notified,snooze_until)
                    VALUES(?,?,?,?,?,?,?,?,0,NULL)""",(p,phone,addr,notes,comp,iso,amt,unit))
        else:
            db_x("""UPDATE appointments SET person=?,phone=?,address=?,notes=?,companions=?,
                    appt_dt=?,remind_amount=?,remind_unit=?,notified=0,snooze_until=NULL WHERE id=?""",
                 (p,phone,addr,notes,comp,iso,amt,unit,self._current_id))
        self.refresh(); self.clear_form(); self.statusBar().showMessage("تم الحفظ/التحديث.")

    def delete_record(self):
        r = self.table.currentRow()
        if r<0: return QMessageBox.information(self,"حذف","اختر سجلًا.")
        _id = int(self.table.item(r,0).text())
        if QMessageBox.question(self,"حذف",f"حذف السجل #{_id}؟")==QMessageBox.Yes:
            db_x("DELETE FROM appointments WHERE id=?",(_id,)); self.refresh(); self.clear_form()

    def mark_done(self):
        r = self.table.currentRow()
        if r<0: return QMessageBox.information(self,"تعليم","اختر سجلًا.")
        _id = int(self.table.item(r,0).text()); db_x("UPDATE appointments SET notified=1, snooze_until=NULL WHERE id=?",(_id,)); self.refresh()

    # --------------------- التذكير ---------------------
    def check_reminders(self):
        now = datetime.datetime.now()
        rows = db_q("""SELECT id, person, companions, appt_dt, remind_amount, remind_unit, notified, snooze_until
                       FROM appointments WHERE notified=0""")
        for _id, person, comp, iso, amt, unit, _, snooze in rows:
            appt = datetime.datetime.fromisoformat(iso)
            if snooze:
                try:
                    if now < datetime.datetime.fromisoformat(snooze): continue
                except: pass
            lead = int(amt)*(86400 if unit=="days" else 3600 if unit=="hours" else 60)
            if 0 <= (appt-now).total_seconds() <= lead:
                dlg = ReminderDialog(person, comp or "", appt, self)
                if dlg.exec()==QDialog.Accepted:
                    if dlg.action=="done":
                        db_x("UPDATE appointments SET notified=1, snooze_until=NULL WHERE id=?",(_id,))
                    elif dlg.action=="snooze":
                        mins = dlg.sno_amt.value()*(60 if dlg.sno_unit.currentText()=="ساعات" else 1)
                        db_x("UPDATE appointments SET snooze_until=? WHERE id=?",
                             ((now+datetime.timedelta(minutes=mins)).isoformat(), _id))
                self.refresh()

    # --------------------- رسم بطاقات ---------------------
    def _draw_list_card(self, p: QPainter, rect: QtCore.QRect, title: str, rows: List[tuple]):
        p.fillRect(rect, QtGui.QColor("#f7f6f3"))
        card = QtCore.QRect(rect.x()+40, rect.y()+40, rect.width()-80, rect.height()-80)
        p.setPen(QtGui.QPen(QtGui.QColor(0,0,0,25), 2)); p.setBrush(QtGui.QColor(255,255,255,220))
        p.drawRoundedRect(card, 26, 26)
        header = QtCore.QRect(card.x()+20, card.y()+20, card.width()-40, 120)
        p.setPen(Qt.NoPen); p.setBrush(QtGui.QColor(255,140,58,235))
        p.drawRoundedRect(header, 16, 16)
        if (lp:=find_image("3")):
            p.drawPixmap(header.x()+26, header.y()+8, QPixmap(lp).scaled(110,110, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        draw_center_title(p, header, title)

        table = QtCore.QRect(card.x()+20, card.y()+160, card.width()-40, card.height()-190)
        p.setPen(QtGui.QPen(QtGui.QColor(0,0,0,30), 2)); p.setBrush(QtGui.QColor(255,255,255,235))
        p.drawRoundedRect(table, 16, 16)

        headers = ["#","الاسم","الهاتف","السكن","التاريخ","الوقت","المرافقون"]
        colw = [60, 270, 220, 240, 200, 140, table.width()-(60+270+220+240+200+140)-30]
        x = table.x()+15; y = table.y()+15; row_h = 48
        p.setPen(QtGui.QColor("#ff8c3a")); p.setFont(QFont("Cairo", 18, QFont.Bold))
        for i,h in enumerate(headers):
            p.drawText(x, y+36, colw[i], row_h, Qt.AlignLeft|Qt.AlignVCenter, h); x += colw[i]
        p.setFont(QFont("Cairo", 16)); p.setPen(QtGui.QColor("#222")); y += row_h + 8
        idx = 1
        for person, phone, addr, iso, comp in rows:
            dt = datetime.datetime.fromisoformat(iso)
            line_rect = QtCore.QRect(table.x()+10, y, table.width()-20, row_h)
            draw_badge(p, line_rect, 10)
            cells = [str(idx), person or "", phone or "", addr or "", dt.strftime("%d/%m/%Y"), dt.strftime("%I:%M %p"), comp or ""]
            x = table.x()+15
            for i,val in enumerate(cells):
                p.drawText(x, y+32, colw[i], row_h, Qt.AlignLeft|Qt.AlignVCenter, val); x += colw[i]
            y += row_h + 4; idx += 1
            if y + row_h > table.bottom()-15: break

    def _draw_person_greeting_card(self, p: QPainter, rect: QtCore.QRect, record: dict):
        p.fillRect(rect, QtGui.QColor("#f7f6f3"))
        card = QtCore.QRect(rect.x()+40, rect.y()+40, rect.width()-80, rect.height()-80)
        p.setPen(QtGui.QPen(QtGui.QColor(0,0,0,25), 2)); p.setBrush(QtGui.QColor(255,255,255,220))
        p.drawRoundedRect(card, 26, 26)

        header = QtCore.QRect(card.x()+20, card.y()+20, card.width()-40, 220)
        p.setPen(Qt.NoPen); p.setBrush(QtGui.QColor(255,140,58,235))
        p.drawRoundedRect(header, 16, 16)

        if (dp:=find_image("2")):
            p.drawPixmap(header.x()+20, header.y()+20, QPixmap(dp).scaled(180,180, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        if (lp:=find_image("3")):
            p.drawPixmap(header.right()-200, header.y()+20, QPixmap(lp).scaled(180,180, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        draw_center_title(p, header, "بطاقة موعد — لقاء الدكتور محمد شويش")

        content = QtCore.QRect(card.x()+40, header.bottom()+30, card.width()-80, card.height()-280)

        name = (record.get("person") or "").strip()
        name_font = QFont("Cairo", 46, QFont.Bold)
        name_rect = QtCore.QRect(content.x(), content.y(), content.width(), 240)
        draw_badge(p, name_rect, 18)
        used_h = draw_wrapped_text(p, name_rect, name, name_font, QtGui.QColor("#111"),
                                   align=Qt.AlignLeft | Qt.AlignTop, rtl=True)

        y = int(content.y() + min(used_h, name_rect.height()) + 26)
        line_h = 58
        info_font = QFont("Cairo", 24, QFont.Medium)

        phone = record.get("phone") or "-"
        addr  = record.get("address") or "-"
        comp  = record.get("companions") or "-"
        try:
            dt = datetime.datetime.fromisoformat(record.get("appt_iso") or "")
            date_str = dt.strftime("%d/%m/%Y")
            time_str = dt.strftime("%I:%M %p")
        except Exception:
            date_str, time_str = "-", "-"

        for L in [
            f"الهاتف: {phone}",
            f"السكن: {addr}",
            f"التاريخ: {date_str}  —  الوقت: {time_str}",
            f"المرافقون: {comp}",
        ]:
            lr = QtCore.QRect(content.x(), y, content.width(), line_h)
            draw_badge(p, lr, 14)
            draw_wrapped_text(p, lr, L, info_font, QtGui.QColor("#111"),
                              align=Qt.AlignLeft | Qt.AlignVCenter, rtl=True)
            y += line_h + 10

        notes_rect = QtCore.QRect(content.x(), y+10, content.width(), content.bottom()-y-20)
        draw_badge(p, notes_rect, 16)
        para_font = QFont("Cairo", 22)
        draw_wrapped_text(p, notes_rect, f"ملاحظات:\n{record.get('notes') or '-'}", para_font, QtGui.QColor("#222"),
                          align=Qt.AlignLeft | Qt.AlignTop, rtl=True)

    # --------------------- حفظ صور PNG ---------------------
    def _export_png(self, painter_fn, default_name: str, *args):
        path, _ = QFileDialog.getSaveFileName(self, "حفظ PNG", default_name, "PNG (*.png)")
        if not path: return
        W, H = 2400, 1600
        img = QtGui.QImage(W, H, QtGui.QImage.Format_ARGB32)
        img.fill(QtGui.QColor("#f2f1ee"))
        p = QPainter(img); p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        painter_fn(p, QtCore.QRect(0,0,W,H), *args)
        p.end(); img.save(path, "PNG")
        QMessageBox.information(self, "تصدير", "تم حفظ الصورة بنجاح.")

    def export_card(self):
        if self.table.rowCount()==0:
            return QMessageBox.information(self,"تصدير","لا توجد بيانات.")
        all_rows=[]
        for r in range(self.table.rowCount()):
            person=self.table.item(r,1).text()
            phone =self.table.item(r,2).text()
            addr  =self.table.item(r,3).text()
            iso   =self.table.item(r,4).data(Qt.UserRole)
            comp  =self.table.item(r,6).text()
            all_rows.append((person,phone,addr,iso,comp))

        dlg = QDialog(self); dlg.setWindowTitle("خيارات التصدير"); dlg.setObjectName("ExportDlg")
        vb = QVBoxLayout(dlg)
        bg = QButtonGroup(dlg)
        rb1 = QRadioButton("بطاقة معايدة كبيرة (السجل المحدد)")
        rb2 = QRadioButton("قائمة — كل النتائج الظاهرة")
        bg.addButton(rb1,1); bg.addButton(rb2,2)
        if self.table.currentRow()>=0: rb1.setChecked(True)
        else: rb2.setChecked(True); rb1.setEnabled(False)
        vb.addWidget(rb1); vb.addWidget(rb2)
        ok = QPushButton("متابعة"); ok.clicked.connect(dlg.accept); vb.addWidget(ok, alignment=Qt.AlignLeft)
        apply_background(dlg,"1")
        if dlg.exec()!=QDialog.Accepted: return
        mode = bg.checkedId()

        if mode==1:
            i = self.table.currentRow()
            if i < 0:
                i = 0
                self.table.selectRow(0)
            person = self.table.item(i,1).text()
            phone  = self.table.item(i,2).text()
            addr   = self.table.item(i,3).text()
            iso    = self.table.item(i,4).data(Qt.UserRole)
            comp   = self.table.item(i,6).text()
            notes  = self.table.item(i,7).text() if self.table.item(i,7) else ""
            record = {"person":person,"phone":phone,"address":addr,"notes":notes,"companions":comp,"appt_iso":iso}
            self._export_png(self._draw_person_greeting_card, f"بطاقة_{person}.png", record)
        else:
            self._export_png(self._draw_list_card, "جدول_مواعيد_الدكتور.png",
                             "جدول مواعيد لقاءات الدكتور محمد شويش", all_rows)

    def export_today_report(self):
        rows = db_q("""SELECT person,phone,address,appt_dt,companions
                       FROM appointments
                       WHERE date(appt_dt)=date('now','localtime')
                       ORDER BY datetime(appt_dt) ASC""")
        if not rows: return QMessageBox.information(self,"تقرير اليوم","لا توجد مواعيد لليوم.")
        self._export_png(self._draw_list_card, "تقرير_اليوم.png",
                         "مواعيد اليوم — الدكتور محمد شويش", rows)

# ===================== تشغيل =====================
def main():
    ensure_db()
    app = QApplication(sys.argv)
    dlg = LoginDialog()
    if dlg.exec()!=QDialog.Accepted: return
    win = MainWindow(); win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
