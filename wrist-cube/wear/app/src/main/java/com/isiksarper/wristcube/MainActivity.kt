package com.isiksarper.wristcube

import android.app.Activity
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.os.VibrationEffect
import android.os.Vibrator
import android.text.InputType
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.Locale
import java.util.concurrent.TimeUnit
import kotlin.math.sqrt

/**
 * Bilek Küpü saat uygulaması.
 * - Yön (quaternion) verisini ~50 Hz ile relay'e gönderir:  {"t":"ori","q":[w,x,y,z]}
 * - Bilekte çift darbe (çift alkış) algılayınca titrer ve gönderir: {"t":"wake"}
 * - "Sıfırla" düğmesi: {"t":"calibrate"}
 */
class MainActivity : Activity(), SensorEventListener {

    private lateinit var sensors: SensorManager
    private lateinit var conn: ConnectivityManager
    private var wifiCallback: ConnectivityManager.NetworkCallback? = null

    private val http = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .pingInterval(10, TimeUnit.SECONDS)
        .build()
    private var ws: WebSocket? = null
    @Volatile private var connected = false

    private val ui = Handler(Looper.getMainLooper())
    private lateinit var status: TextView
    private lateinit var urlField: EditText

    private val quat = FloatArray(4)
    private var lastSendNs = 0L

    // Çift darbe algılama
    private var firstHitMs = 0L
    private var lastHitMs = 0L
    private var lastWakeMs = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        sensors = getSystemService(SENSOR_SERVICE) as SensorManager
        conn = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val prefs = getPreferences(MODE_PRIVATE)

        val pad = (resources.displayMetrics.density * 18).toInt()
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(pad, pad * 2, pad, pad * 2)
        }
        col.addView(TextView(this).apply { text = "Bilek Küpü"; textSize = 16f; gravity = Gravity.CENTER })
        urlField = EditText(this).apply {
            setText(prefs.getString("url", "ws://192.168.1.20:8765/ws"))
            textSize = 12f
            isSingleLine = true
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        col.addView(urlField)
        col.addView(Button(this).apply {
            text = "Bağlan"
            setOnClickListener {
                prefs.edit().putString("url", urlField.text.toString().trim()).apply()
                connect()
            }
        })
        col.addView(Button(this).apply {
            text = "Sıfırla"
            setOnClickListener { send("{\"t\":\"calibrate\"}") }
        })
        status = TextView(this).apply { text = "Bağlı değil"; textSize = 12f; gravity = Gravity.CENTER }
        col.addView(status)
        setContentView(ScrollView(this).apply { addView(col) })

        requestWifi()
    }

    /** Saat normalde trafiği telefon üzerinden Bluetooth ile geçirir; yerel ağa ulaşmak için Wi-Fi iste. */
    private fun requestWifi() {
        val request = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .build()
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                conn.bindProcessToNetwork(network)
                setStatus("Wi-Fi hazır")
            }
            override fun onLost(network: Network) {
                conn.bindProcessToNetwork(null)
                setStatus("Wi-Fi koptu")
            }
        }
        wifiCallback = cb
        conn.requestNetwork(request, cb)
    }

    private fun connect() {
        ws?.close(1000, null)
        connected = false
        val request = try {
            Request.Builder().url(urlField.text.toString().trim()).build()
        } catch (e: IllegalArgumentException) {
            setStatus("Adres geçersiz"); return
        }
        setStatus("Bağlanıyor…")
        ws = http.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                connected = true; setStatus("Bağlandı")
            }
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                connected = false; setStatus("Kapandı")
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                connected = false; setStatus("Hata: " + (t.message ?: t.javaClass.simpleName))
            }
        })
    }

    override fun onResume() {
        super.onResume()
        // GAME_ROTATION_VECTOR manyetometre kullanmaz: iç mekânda daha az titrer, yaw yavaşça kayabilir (Sıfırla ile düzelir).
        val rot = sensors.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR)
            ?: sensors.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
        rot?.let { sensors.registerListener(this, it, 20_000) }          // ~50 Hz
        sensors.getDefaultSensor(Sensor.TYPE_LINEAR_ACCELERATION)
            ?.let { sensors.registerListener(this, it, 10_000) }         // ~100 Hz
    }

    override fun onPause() {
        super.onPause()
        sensors.unregisterListener(this)
    }

    override fun onDestroy() {
        super.onDestroy()
        ws?.close(1000, null)
        wifiCallback?.let { conn.unregisterNetworkCallback(it) }
        conn.bindProcessToNetwork(null)
    }

    override fun onSensorChanged(e: SensorEvent) {
        when (e.sensor.type) {
            Sensor.TYPE_GAME_ROTATION_VECTOR, Sensor.TYPE_ROTATION_VECTOR -> {
                if (e.timestamp - lastSendNs < 18_000_000L) return
                lastSendNs = e.timestamp
                SensorManager.getQuaternionFromVector(quat, e.values) // [w, x, y, z]
                // Locale.US: Türkçe yerel ayarda ondalık ayırıcı virgül olur ve JSON bozulur.
                send(String.format(Locale.US, "{\"t\":\"ori\",\"q\":[%.5f,%.5f,%.5f,%.5f]}",
                    quat[0], quat[1], quat[2], quat[3]))
            }
            Sensor.TYPE_LINEAR_ACCELERATION -> detectDoubleHit(e.values)
        }
    }

    /** İki keskin darbe, arada 120–600 ms → uyandır. Eşiği kendi alkışına göre ayarla. */
    private fun detectDoubleHit(v: FloatArray) {
        val mag = sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
        if (mag < HIT_THRESHOLD) return
        val now = SystemClock.elapsedRealtime()
        if (now - lastHitMs < 90) { lastHitMs = now; return } // aynı darbenin devamı
        lastHitMs = now
        val gap = now - firstHitMs
        if (gap in 120..600 && now - lastWakeMs > 1000) {
            lastWakeMs = now
            firstHitMs = 0
            send("{\"t\":\"wake\"}")
            buzz()
        } else {
            firstHitMs = now
        }
    }

    @Suppress("DEPRECATION")
    private fun buzz() {
        getSystemService(Vibrator::class.java)
            ?.vibrate(VibrationEffect.createOneShot(40, VibrationEffect.DEFAULT_AMPLITUDE))
    }

    private fun send(text: String) {
        if (connected) ws?.send(text)
    }

    private fun setStatus(s: String) {
        ui.post { status.text = s }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    companion object {
        private const val HIT_THRESHOLD = 14f // m/s²
    }
}
