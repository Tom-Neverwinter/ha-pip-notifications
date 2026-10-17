#!/usr/bin/env bash
# Gradle-free build: javac -> d8 -> aapt2 link -> zipalign -> apksigner. Output: build/ha-pip-notifications.apk
set -euo pipefail
cd "$(dirname "$0")"
SDK="${ANDROID_HOME:-$LOCALAPPDATA/Android/Sdk}"
BT="$SDK/build-tools/35.0.0"
JAR="$SDK/platforms/android-35/android.jar"
KS="${HAPIP_KEYSTORE:-$HOME/.android/debug.keystore}"
export _JAVA_OPTIONS="-Xmx1g"   # this PC sets a 256M global cap that starves the tools

rm -rf build && mkdir -p build/classes build/dex
mapfile -t SRC < <(find src -name '*.java')
javac -source 11 -target 11 -Xlint:-options -encoding UTF-8 -cp "$JAR" -d build/classes "${SRC[@]}"
mapfile -t CLS < <(find build/classes -name '*.class')
"$BT/d8.bat" --release --min-api 26 --lib "$JAR" --output build/dex "${CLS[@]}"
"$BT/aapt2.exe" link --manifest AndroidManifest.xml -I "$JAR" -o build/unsigned.apk
(cd build/dex && python -c "import zipfile;z=zipfile.ZipFile('../unsigned.apk','a');z.write('classes.dex');z.close()")
"$BT/zipalign.exe" -f -p 4 build/unsigned.apk build/aligned.apk

# ponytail: Android debug keystore is fine for a sideloaded home app; keep it, updates need the same key.
[ -f "$KS" ] || keytool -genkeypair -keystore "$KS" -storepass android -keypass android -alias androiddebugkey \
  -dname "CN=Android Debug,O=Android,C=US" -keyalg RSA -keysize 2048 -validity 10000
"$BT/apksigner.bat" sign --ks "$KS" --ks-pass pass:android --out build/ha-pip-notifications.apk build/aligned.apk
"$BT/apksigner.bat" verify build/ha-pip-notifications.apk && ls -l build/ha-pip-notifications.apk
