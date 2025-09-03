Taqaddum Appointments — Android Build (PySide6)

الملفات بجانب هذا المستند:
- main.py    (ملف البرنامج)
- 1.png / 2.png / 3.png  (الخلفية/صورة الدكتور/الشعار)
- pysidedeploy.spec       (ملف إعداد النشر)

الخطوات داخل Ubuntu/WSL (قص ولصق):

1) المتطلبات (لو لم تُثبت سابقًا):
   sudo apt update
   sudo apt install -y python3.11 python3.11-venv openjdk-17-jdk git zip unzip android-tools-adb

2) تنزيل SDK/NDK تلقائيًا (مرة واحدة):
   git clone https://code.qt.io/pyside/pyside-setup
   python3 pyside-setup/tools/cross_compile_android/main.py --download-only --skip-update --auto-accept-license

3) بيئة بايثون + PySide6 + qtpip:
   python3.11 -m venv ~/.venvs/taqaddum && source ~/.venvs/taqaddum/bin/activate
   python -m pip install --upgrade pip PySide6 qtpip

4) تنزيل عجلات PySide6 للأندرويد (aarch64) ووضعها في ~/wheels :
   mkdir -p ~/wheels
   qtpip download PySide6 --android --arch aarch64
   qtpip download Shiboken6 --android --arch aarch64
   # تأكد من أسماء الملفات الناتجة وحدثها داخل pysidedeploy.spec (wheel_pyside / wheel_shiboken)

5) ادخل إلى مجلد المشروع الذي يحتوي هذا الملف ثم ابنِ الـ APK:
   source ~/.venvs/taqaddum/bin/activate
   pyside6-android-deploy --config-file pysidedeploy.spec -v --keep-deployment-files

6) تثبيت على الهاتف عبر ADB (Wi‑Fi أو USB):
   adb devices
   adb install -r dist/*debug*.apk

ملاحظات:
- لو لم تُدرج الصور، تأكد أن أسماء الملفات 1/2/3 مطابقة وأنها بجانب main.py.
- لو ظهر خطأ فقدان wheel_pyside/shiboken: صحّح المسارات داخل pysidedeploy.spec.
- لو أردت AAB (للنشر)، عدّل mode=release ثم وفّر توقيع keystore عبر buildozer (تلقائيًا يتم إنشاؤه أول مرة).
