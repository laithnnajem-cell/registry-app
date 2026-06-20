[app]

# اسم التطبيق الذي يظهر تحت الأيقونة
title = أرشفة سجلات القيد

# الاسم البرمجي للحزمة (بالإنجليزية فقط، بدون مسافات)
package.name = registryapp

# دومين عكسي فريد لتطبيقك (غيّره لاسمك إذا رغبت)
package.domain = org.registry

# مجلد المصدر (المكان الذي فيه main.py)
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,db

# نسخة التطبيق
version = 1.0

# المتطلبات (المكتبات) التي يحتاجها التطبيق
# python3, kivy, kivymd: الواجهة
# pillow: معالجة الصور وتصدير PDF
# plyer: الوصول للكاميرا/المعرض ومشاركة ملفات PDF (يدير FileProvider داخلياً)
requirements = python3,kivy==2.3.0,kivymd==1.2.0,pillow,plyer,sqlite3

# الأيقونة (اختياري - ضع ملف icon.png بحجم 512x512 في نفس المجلد إذا رغبت)
# icon.filename = %(source.dir)s/icon.png

# اتجاه الشاشة: portrait (طولي) أو landscape (عرضي) أو all
orientation = portrait

# دعم النصوص العربية - يضمن تحميل خط يدعم العربية بشكل صحيح
fullscreen = 0

#
# الصلاحيات المطلوبة على أندرويد
#
android.permissions = CAMERA,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES,INTERNET

# الحد الأدنى والمستهدف لإصدار Android API
android.minapi = 24
android.api = 34
android.ndk = 25b
android.sdk = 34

# نوع البنية (arm64-v8a يغطي أغلب الأجهزة الحديثة، armeabi-v7a للأجهزة القديمة)
android.archs = arm64-v8a, armeabi-v7a

# يسمح بقراءة وكتابة الملفات (لتصدير PDF لمجلد Downloads)
android.allow_backup = True

# اسم نشاط Python الرئيسي (تلقائي عادة، لا حاجة لتغييره)
# android.entrypoint = org.kivy.android.PythonActivity

[buildozer]

# مستوى السجلات: 0 = هادئ، 1 = عادي، 2 = تفصيلي (مفيد عند حدوث أخطاء)
log_level = 2

# تحذير عند التشغيل بصلاحية root (اتركه كما هو)
warn_on_root = 1
