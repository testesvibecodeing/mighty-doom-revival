package br.com.revival.auth;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.text.method.PasswordTransformationMethod;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.ByteArrayOutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Tela de autenticacao do Revival: unico MAIN/LAUNCHER do APK.
 *
 * Fluxo (maquina de estados do prompt de especificacao):
 *
 *   START -> credenciais validas -> abre a Activity Unity
 *         -> sem credenciais     -> AUTH_SCREEN
 *   AUTH_SCREEN -> Criar conta -> register real -> grava -> mostra recovery -> Unity
 *               -> Entrar      -> login-device real -> grava -> Unity
 *               -> erro de rede/credencial -> permanece na tela, com mensagem
 *
 * Contratos REAIS, medidos (nao inventados):
 *
 *   - `credentials.json` vive em getExternalFilesDir(null) — o mesmo caminho que
 *     `Ubu.CredentialStore` le (medido no dispositivo: /storage/emulated/0/
 *     Android/data/com.bethsoft.ubu/files/credentials.json);
 *   - schema v3: version, user_id, device_id, password, region, platform
 *     (metadata v29: CredentialStore.SaveData; conferido no arquivo real);
 *   - `device_id` NAO e inventado: vem do response de register
 *     (CredentialStore.Create recebe deviceId como parametro);
 *   - guard de toda rota /game/*: POST + x-ubu-apiversion + content-type JSON;
 *   - prefixo /collections/<slug> preservado na base URL;
 *   - envelope de resposta: { uts, code, ... } com code 1000 = sucesso.
 *
 * Segredo NUNCA vai para log, Intent ou Toast. A gravacao e atomica
 * (arquivo temporario + rename), igual ao CredentialStore.TempPath do cliente.
 */
public final class RevivalAuthActivity extends Activity {

    /** Preenchidos na injecao pelo patcher Python (scripts/patch_revival_auth.py). */
    private static final String BASE_URL = "@@REVIVAL_BASE_URL@@";
    private static final String API_VERSION = "@@REVIVAL_API_VERSION@@";
    private static final String CLIENT_VERSION = "@@REVIVAL_CLIENT_VERSION@@";
    private static final String UNITY_ACTIVITY = "@@REVIVAL_UNITY_ACTIVITY@@";

    private static final String CREDENTIALS_FILE = "credentials.json";
    private static final String GPG_FILE = "gpg.config";
    private static final int SAVE_DATA_VERSION = 3;
    private static final int PLATFORM_ID = 4;
    private static final String REGION = "US";
    private static final int TIMEOUT_MS = 20000;

    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler ui = new Handler(Looper.getMainLooper());

    private EditText userIdField;
    private EditText passwordField;
    private Button createButton;
    private Button loginButton;
    private Button showPasswordButton;
    private TextView statusView;
    private boolean busy;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        // Suprime o gate do Google Play Games ANTES de a Unity subir: o cliente
        // le gpg.config no boot e, com hasCancelledLogin=true, segue direto para
        // o device auth. Escrito aqui porque a Activity roda antes da Unity.
        writeGpgConfigIfMissing();

        if (hasValidCredentials()) {
            launchUnity();
            return;
        }
        setContentView(buildLayout());
    }

    @Override
    protected void onDestroy() {
        worker.shutdownNow();
        super.onDestroy();
    }

    // ---------------------------------------------------------------- UI ----

    private View buildLayout() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.parseColor("#0B0F14"));
        int pad = dp(24);
        root.setPadding(pad, dp(48), pad, pad);

        TextView title = new TextView(this);
        title.setText("MIGHTY DOOM REVIVAL");
        title.setTextColor(Color.parseColor("#7FD41B"));
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 24);
        title.setGravity(Gravity.CENTER);
        root.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("Servidor da comunidade. Entre com sua conta Revival ou crie uma nova.");
        subtitle.setTextColor(Color.parseColor("#A8B3BD"));
        subtitle.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        subtitle.setGravity(Gravity.CENTER);
        subtitle.setPadding(0, dp(8), 0, dp(28));
        root.addView(subtitle);

        userIdField = new EditText(this);
        userIdField.setHint("ID da conta (número)");
        userIdField.setInputType(InputType.TYPE_CLASS_NUMBER);
        userIdField.setTextColor(Color.WHITE);
        userIdField.setHintTextColor(Color.parseColor("#5A6672"));
        root.addView(userIdField);

        passwordField = new EditText(this);
        passwordField.setHint("Senha da conta");
        passwordField.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        passwordField.setTransformationMethod(PasswordTransformationMethod.getInstance());
        passwordField.setTextColor(Color.WHITE);
        passwordField.setHintTextColor(Color.parseColor("#5A6672"));
        root.addView(passwordField);

        showPasswordButton = new Button(this);
        showPasswordButton.setText("Mostrar senha");
        showPasswordButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { togglePassword(); }
        });
        root.addView(showPasswordButton);

        loginButton = new Button(this);
        loginButton.setText("ENTRAR");
        loginButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { onLogin(); }
        });
        root.addView(loginButton);

        createButton = new Button(this);
        createButton.setText("CRIAR CONTA");
        createButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { onCreate(); }
        });
        root.addView(createButton);

        statusView = new TextView(this);
        statusView.setTextColor(Color.parseColor("#E8EDF2"));
        statusView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        statusView.setPadding(0, dp(20), 0, 0);
        statusView.setTextIsSelectable(true);   // recovery code copiável
        root.addView(statusView);

        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.parseColor("#0B0F14"));
        scroll.addView(root, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return scroll;
    }

    private int dp(int value) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value,
                getResources().getDisplayMetrics());
    }

    private void togglePassword() {
        boolean oculto = passwordField.getTransformationMethod() != null;
        passwordField.setTransformationMethod(oculto ? null : PasswordTransformationMethod.getInstance());
        showPasswordButton.setText(oculto ? "Ocultar senha" : "Mostrar senha");
        passwordField.setSelection(passwordField.getText().length());
    }

    /** Bloqueia clique duplo enquanto uma chamada está em voo. */
    private void setBusy(boolean value) {
        busy = value;
        createButton.setEnabled(!value);
        loginButton.setEnabled(!value);
        showPasswordButton.setEnabled(!value);
    }

    private void status(String message) {
        statusView.setText(message);
    }

    // ------------------------------------------------------------- fluxo ----

    private void onCreate() {
        if (busy) return;
        setBusy(true);
        status("Criando conta no servidor Revival…");
        worker.execute(new Runnable() {
            @Override public void run() {
                try {
                    JSONObject body = new JSONObject();
                    body.put("platform_id", PLATFORM_ID);
                    body.put("client_version", CLIENT_VERSION);
                    body.put("region", REGION);
                    final JSONObject response = post("/game/auth/register", body);
                    final Credentials creds = Credentials.fromResponse(response);
                    saveCredentials(creds);
                    final String recovery = response.optString("recovery_code", "");
                    ui.post(new Runnable() {
                        @Override public void run() {
                            // ID e recovery são o que o jogador precisa anotar
                            // para reentrar. A SENHA nunca é exibida nem logada.
                            status("Conta criada.\n\nID: " + creds.userId
                                    + (recovery.isEmpty() ? "" : "\nCódigo de recuperação: " + recovery)
                                    + "\n\nAnote antes de continuar. Abrindo o jogo…");
                            ui.postDelayed(new Runnable() {
                                @Override public void run() { launchUnity(); }
                            }, 6000);
                        }
                    });
                } catch (final Exception error) {
                    failOnUi(error);
                }
            }
        });
    }

    private void onLogin() {
        if (busy) return;
        final String rawId = userIdField.getText().toString().trim();
        final String password = passwordField.getText().toString();
        if (rawId.isEmpty() || password.isEmpty()) {
            status("Informe o ID da conta e a senha.");
            return;
        }
        final long userId;
        try {
            userId = Long.parseLong(rawId);
        } catch (NumberFormatException invalid) {
            status("O ID da conta é numérico.");
            return;
        }
        setBusy(true);
        status("Entrando…");
        worker.execute(new Runnable() {
            @Override public void run() {
                try {
                    JSONObject body = new JSONObject();
                    body.put("client_version", CLIENT_VERSION);
                    body.put("user_id", userId);
                    body.put("password", password);
                    JSONObject response = post("/game/auth/login-device", body);
                    Credentials creds = Credentials.fromLogin(response, userId, password);
                    saveCredentials(creds);
                    ui.post(new Runnable() {
                        @Override public void run() {
                            status("Autenticado. Abrindo o jogo…");
                            launchUnity();
                        }
                    });
                } catch (final Exception error) {
                    failOnUi(error);
                }
            }
        });
    }

    private void failOnUi(final Exception error) {
        // Mensagem por CLASSE de erro: rede, credencial e servidor são
        // situações diferentes para o jogador. Nunca ecoa segredo.
        final String message;
        if (error instanceof ApiException) {
            int code = ((ApiException) error).code;
            if (code == 2101 || code == 2102) message = "ID ou senha não conferem.";
            else if (code == 2010 || code == 2011) message = "Versão do cliente incompatível com o servidor.";
            else if (code >= 3000) message = "O servidor Revival respondeu com erro. Tente de novo em instantes.";
            else message = "Não foi possível autenticar (código " + code + ").";
        } else {
            message = "Sem conexão com o servidor Revival. Verifique a rede e tente de novo.";
        }
        ui.post(new Runnable() {
            @Override public void run() {
                setBusy(false);
                status(message);
            }
        });
    }

    // --------------------------------------------------------------- HTTP ---

    private static final class ApiException extends Exception {
        final int code;
        ApiException(int code) { super("code " + code); this.code = code; }
    }

    private JSONObject post(String path, JSONObject body) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(BASE_URL + path).openConnection();
        try {
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(TIMEOUT_MS);
            conn.setReadTimeout(TIMEOUT_MS);
            conn.setDoOutput(true);
            conn.setRequestProperty("content-type", "application/json");
            conn.setRequestProperty("x-ubu-apiversion", API_VERSION);
            byte[] payload = body.toString().getBytes(StandardCharsets.UTF_8);
            OutputStream out = conn.getOutputStream();
            out.write(payload);
            out.close();

            int status = conn.getResponseCode();
            InputStream stream = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
            String text = readAll(stream);
            JSONObject json = new JSONObject(text);
            int code = json.optInt("code", -1);
            if (status != 200 || code != 1000) throw new ApiException(code);
            return json;
        } finally {
            conn.disconnect();
        }
    }

    private static String readAll(InputStream stream) throws Exception {
        if (stream == null) return "{}";
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        byte[] chunk = new byte[4096];
        int read;
        while ((read = stream.read(chunk)) != -1) buffer.write(chunk, 0, read);
        stream.close();
        return new String(buffer.toByteArray(), StandardCharsets.UTF_8);
    }

    // -------------------------------------------------------- credenciais ---

    private static final class Credentials {
        final long userId;
        final String deviceId;
        final String password;

        Credentials(long userId, String deviceId, String password) {
            this.userId = userId;
            this.deviceId = deviceId;
            this.password = password;
        }

        /** register devolve user_id, device_id e password — nada é inventado. */
        static Credentials fromResponse(JSONObject json) throws Exception {
            long id = json.getLong("user_id");
            String device = json.getString("device_id");
            String password = json.getString("password");
            if (device.length() != 36 || password.isEmpty()) {
                throw new Exception("resposta de register fora do contrato");
            }
            return new Credentials(id, device, password);
        }

        /**
         * O `device_id` da conta, vindo do próprio response — nunca inventado.
         *
         * `login-device` não devolve `device_id` (ele vai no REQUEST, porque a
         * rota pressupõe um dispositivo que já tem credenciais). Mas devolve
         * `puuid`, e os dois são o MESMO valor:
         *
         *   register  -> `device_id: body.device_id || user.uuid`  (index.js:595)
         *   login     -> `puuid: user.uuid`                        (loginUser)
         *
         * e nem o cliente Unity nem esta Activity enviam `device_id` no
         * register (fixture real: `{platform_id, client_version, region}`), ou
         * seja, `device_id == user.uuid == puuid` para toda conta Revival.
         *
         * Ordem de preferência mesmo assim: `device_id` explícito, se algum dia
         * a rota passar a devolvê-lo; depois `puuid`. Sem nenhum dos dois,
         * falha explícita — nunca um UUID gerado aqui.
         */
        static Credentials fromLogin(JSONObject json, long userId, String password) throws Exception {
            String device = json.optString("device_id", "");
            if (device.length() != 36) device = json.optString("puuid", "");
            if (device.length() != 36) {
                throw new Exception("login sem device_id nem puuid utilizável");
            }
            return new Credentials(userId, device, password);
        }

        JSONObject toJson() throws Exception {
            JSONObject json = new JSONObject();
            json.put("version", SAVE_DATA_VERSION);
            json.put("user_id", userId);
            json.put("device_id", deviceId);
            json.put("password", password);
            json.put("region", REGION);
            json.put("platform", PLATFORM_ID);
            return json;
        }
    }

    private File credentialsFile() {
        return new File(getExternalFilesDir(null), CREDENTIALS_FILE);
    }

    private boolean hasValidCredentials() {
        File file = credentialsFile();
        if (!file.isFile() || file.length() == 0) return false;
        try {
            JSONObject json = new JSONObject(readAll(new java.io.FileInputStream(file)));
            return json.optInt("version", 0) == SAVE_DATA_VERSION
                    && json.optLong("user_id", 0) > 0
                    && json.optString("device_id", "").length() == 36
                    && !json.optString("password", "").isEmpty();
        } catch (Exception broken) {
            // Arquivo corrompido volta para a tela em vez de derrubar o app.
            return false;
        }
    }

    /** Gravação atômica: temporário no MESMO diretório + rename. */
    private void saveCredentials(Credentials creds) throws Exception {
        File target = credentialsFile();
        File parent = target.getParentFile();
        if (parent != null) parent.mkdirs();
        File temp = new File(parent, ".credentials-" + System.nanoTime() + ".tmp");
        FileOutputStream out = new FileOutputStream(temp);
        try {
            out.write(creds.toJson().toString().getBytes(StandardCharsets.UTF_8));
            out.getFD().sync();
        } finally {
            out.close();
        }
        if (!temp.renameTo(target)) {
            temp.delete();
            throw new Exception("não foi possível gravar as credenciais");
        }
    }

    /**
     * `gpg.config` = GooglePlayLocalConfig do .NET com hasCancelledLogin=true e
     * hasLoggedOut=false. Layout fixo de 180 bytes, reproduzido byte a byte a
     * partir do arquivo real do dispositivo (ver scripts/revival_auth/gpg_config.py,
     * que tem o round-trip provado em teste).
     */
    private void writeGpgConfigIfMissing() {
        try {
            File file = new File(getExternalFilesDir(null), GPG_FILE);
            if (file.isFile() && file.length() > 0) return;
            File parent = file.getParentFile();
            if (parent != null) parent.mkdirs();
            FileOutputStream out = new FileOutputStream(file);
            try {
                out.write(gpgConfigBytes());
                out.getFD().sync();
            } finally {
                out.close();
            }
        } catch (Exception ignored) {
            // Falhar aqui não impede autenticar: o popup Google apenas reaparece.
        }
    }

    private static byte[] gpgConfigBytes() {
        String assembly = "Ubu.GooglePlay, Version=0.0.0.0, Culture=neutral, PublicKeyToken=null";
        String typeName = "Ubu.GooglePlay.GooglePlayLocalConfig";
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(0x00);                       // SerializedStreamHeader
        writeInt(out, 1); writeInt(out, -1); writeInt(out, 1); writeInt(out, 0);
        out.write(0x0C); writeInt(out, 2);     // BinaryLibrary id=2
        writeString(out, assembly);
        out.write(0x05); writeInt(out, 1);     // ClassWithMembersAndTypes id=1
        writeString(out, typeName);
        writeInt(out, 2);                      // memberCount
        writeString(out, "hasCancelledLogin");
        writeString(out, "hasLoggedOut");
        out.write(0x00); out.write(0x00);      // BinaryTypeEnum.Primitive x2
        out.write(0x01); out.write(0x01);      // PrimitiveTypeEnum.Boolean x2
        writeInt(out, 2);                      // libraryId
        out.write(0x01);                       // hasCancelledLogin = true
        out.write(0x00);                       // hasLoggedOut = false
        out.write(0x0B);                       // MessageEnd
        return out.toByteArray();
    }

    private static void writeInt(ByteArrayOutputStream out, int value) {
        out.write(value & 0xFF);
        out.write((value >> 8) & 0xFF);
        out.write((value >> 16) & 0xFF);
        out.write((value >> 24) & 0xFF);
    }

    private static void writeString(ByteArrayOutputStream out, String value) {
        byte[] raw = value.getBytes(StandardCharsets.UTF_8);
        int length = raw.length;
        while (true) {                          // 7-bit encoded int
            int b = length & 0x7F;
            length >>= 7;
            if (length != 0) out.write(b | 0x80);
            else { out.write(b); break; }
        }
        out.write(raw, 0, raw.length);
    }

    // -------------------------------------------------------------- Unity ---

    /**
     * Abre a Activity Unity ORIGINAL, preservada no Manifest com todos os seus
     * filtros e metadados. Só o filtro MAIN/LAUNCHER migrou para cá.
     */
    private void launchUnity() {
        try {
            Intent intent = new Intent();
            intent.setClassName(getPackageName(), UNITY_ACTIVITY);
            intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP);
            startActivity(intent);
            finish();
        } catch (Exception error) {
            Toast.makeText(this, "Não foi possível abrir o jogo.", Toast.LENGTH_LONG).show();
            setBusy(false);
        }
    }
}
