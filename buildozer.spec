[app]
title = DiscordiaVPN
package.name = discordiavpn
package.domain = org.discordia
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.0.0

requirements = python3,kivy==2.3.0,pyjnius,android,pillow,certifi

icon.filename = icon.png
presplash.filename = presplash.png
presplash.color = #070912

orientation = portrait
fullscreen = 0

# ─── Android specific ───
android.permissions =
    INTERNET,
    ACCESS_NETWORK_STATE,
    ACCESS_WIFI_STATE,
    FOREGROUND_SERVICE,
    RECEIVE_BOOT_COMPLETED

# Grant the BIND_VPN_SERVICE permission (required for VPNService)
android.manifest_placeholders = appAuthRedirectScheme:discordiavpn

# Java source files for VPNService
android.add_src = java_src

# AndroidManifest additions
android.manifest_extra =
    <service
        android:name="org.discordia.vpn.DiscordiaVPNService"
        android:permission="android.permission.BIND_VPN_SERVICE"
        android:exported="false">
        <intent-filter>
            <action android:name="android.net.VpnService"/>
        </intent-filter>
    </service>

android.api = 33
android.minapi = 24
android.ndk = 25b
android.sdk = 33
android.accept_sdk_license = True

android.arch = arm64-v8a

# Gradle dependencies
android.gradle_dependencies =

# Enable AndroidX
android.enable_androidx = True

# Set the app theme for dark mode
android.apptheme = @style/Theme.AppCompat.NoActionBar

# Build mode
android.release_artifact = apk
android.debug_artifact = apk

p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1