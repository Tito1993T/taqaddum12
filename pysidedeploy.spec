# pysidedeploy.spec — إعداد نشر PySide6 للأندرويد
# ملاحظة: عدّل المسارات أدناه (wheel_pyside / wheel_shiboken) بحسب مكان تنزيل عجلات الأندرويد لديك.

[app]
title = Taqaddum Appointments
# ملف الدخول يجب أن يكون main.py في نفس المجلد
input_file = main.py

[python]
# مسار بايثون داخل بيئتك الافتراضية في WSL/Ubuntu (عدّله عندك إن اختلف)
python_path = ~/.venvs/taqaddum/bin/python

[android]
# معماريات الحزم؛ أغلب الأجهزة الحديثة aarch64
arch = aarch64
# ضع المسارات الفعلية لملفات عجلات PySide6/Shiboken للأندرويد التي نزّلتها باستخدام qtpip
wheel_pyside = ~/wheels/PySide6-android-aarch64.whl
wheel_shiboken = ~/wheels/shiboken6-android-aarch64.whl
# إن رغبت تحديد SDK/NDK يدويًا (اختياري)، أزل التعليق وعدّل المسارات
# sdk_path = ~/.pyside6-android-deploy/android_sdk
# ndk_path = ~/.pyside6-android-deploy/android_ndk

[buildozer]
# debug = APK, release = AAB (للنشر على المتجر تجهّز Keystore لاحقًا)
mode = debug
# تضمين امتدادات الصور والخطوط إلى الحِزمة
extra_args = --include-exts=py,png,jpg,jpeg,ttf
