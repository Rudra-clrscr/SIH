[app]
title = Smart Tourist Safety
package.name = smarttourist
package.domain = org.astra.safety
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,db,env,html,css,js
version = 1.0
requirements = python3,kivy,flask,sqlalchemy,flask-sqlalchemy,numpy,scikit-learn,twilio,python-dotenv,jnius
orientation = portrait
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/splash.png

[android]
android.permissions = INTERNET, VIBRATE
android.api = 31
android.minapi = 21
android.sdk = 24
android.ndk = 19c
android.arch = armeabi-v7a,arm64-v8a
p4a.branch = master