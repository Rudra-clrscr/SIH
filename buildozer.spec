[app]
title = Smart Tourist Safety
package.name = smarttourist
package.domain = org.astra.safety
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,db,env,html,css,js
version = 1.0
requirements = python3,kivy,flask,sqlalchemy,flask-sqlalchemy,numpy,scikit-learn,twilio,python-dotenv,jnius
orientation = portrait

[android]
android.permissions = INTERNET, VIBRATE
android.arch = armeabi-v7a,arm64-v8a
p4a.branch = master