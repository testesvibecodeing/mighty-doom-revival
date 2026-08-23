package br.com.revival.auth;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.text.method.PasswordTransformationMethod;
import android.util.Base64;
import android.util.TypedValue;
import android.util.Patterns;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
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
 *   START -> credencial gravada -> PREFLIGHT (game/auth/login-device)
 *              preflight 1000        -> abre a Activity Unity
 *              preflight 403/2101    -> apaga a credencial -> AUTH_SCREEN
 *              preflight sem rede    -> AUTH_SCREEN com "tentar de novo"
 *         -> sem credencial     -> AUTH_SCREEN
 *   AUTH_SCREEN -> Criar conta -> abre /account?mode=register no domínio Revival
 *               -> Entrar      -> e-mail/senha
 *                                   senha permanente -> grava credencial -> Unity
 *                                   senha temporária -> NEW_PASSWORD_SCREEN
 *               -> Esqueci     -> SMTP envia senha temporária, se configurado
 *               -> erro de rede/credencial -> permanece na tela, com mensagem
 *   NEW_PASSWORD_SCREEN -> /account/password -> grava credencial NOVA -> Unity
 *
 * Por que o PREFLIGHT existe (dead-end fechado, nao contornado): o
 * `credentials.json` guarda a SENHA, e a senha pode mudar no site depois de o
 * arquivo ter sido escrito. Sem verificar, o boot seguinte pularia esta tela e
 * morreria no `login-device` com 2101, sem caminho de volta para o jogador. O
 * preflight usa a MESMA rota que a Unity vai usar — nada inventado — e por isso
 * mede exatamente a condicao que importa.
 *
 * E por que a NEW_PASSWORD_SCREEN e obrigatoria: gravar a senha TEMPORARIA no
 * arquivo criaria o mesmo dead-end de proposito, ja que ela expira e e trocada.
 * A credencial persistida e sempre uma senha permanente.
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

    /** Fundo (embers/glow) opcional, injetado em BUILD TIME a partir de um
     * PNG local (nunca versionado - ver scripts/revival_auth/build.py). Sem
     * fundo configurado o placeholder vira um array vazio e a Activity cai
     * no fundo solido (ver decodeBackground()/root.setBackgroundColor). */
    private static final String[] BG_B64 = { @@REVIVAL_BG_B64_ENTRIES@@ };

    private static final String CREDENTIALS_FILE = "credentials.json";
    private static final String GPG_FILE = "gpg.config";
    private static final int SAVE_DATA_VERSION = 3;
    private static final int PLATFORM_ID = 4;
    private static final String REGION = "US";
    private static final int TIMEOUT_MS = 20000;

    private static final int COLOR_PANEL_FILL = Color.parseColor("#D91A120E");
    private static final int COLOR_PANEL_BORDER = Color.parseColor("#8FE8792B");
    private static final int COLOR_FIELD_FILL = Color.parseColor("#40140D0A");
    private static final int COLOR_FIELD_BORDER = Color.parseColor("#4A3327");
    private static final int COLOR_PILL_FILL = Color.parseColor("#CC1F140F");
    private static final int COLOR_ACCENT = Color.parseColor("#F2A93B");
    private static final int COLOR_TEXT_PRIMARY = Color.parseColor("#ECE5DC");
    private static final int COLOR_TEXT_MUTED = Color.parseColor("#B0A296");
    private static final int COLOR_BUTTON_START = Color.parseColor("#EE5A2B");
    private static final int COLOR_BUTTON_END = Color.parseColor("#901414");
    private static final int COLOR_STATUS_BORDER = Color.parseColor("#8FE8542C");
    private static final int COLOR_STATUS_FILL = Color.parseColor("#59180D08");
    private static final int COLOR_OK_DOT = Color.parseColor("#63D471");
    private static final int COLOR_SHADOW = Color.parseColor("#66000000");

    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler ui = new Handler(Looper.getMainLooper());

    private EditText emailField;
    private EditText passwordField;
    private Button createButton;
    private Button loginButton;
    private Button forgotButton;
    private Button showPasswordButton;
    private Button retryButton;
    private TextView statusView;
    private boolean busy;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        // Suprime o gate do Google Play Games ANTES de a Unity subir: o cliente
        // le gpg.config no boot e, com hasCancelledLogin=true, segue direto para
        // o device auth. Escrito aqui porque a Activity roda antes da Unity.
        writeGpgConfigIfMissing();

        setContentView(buildLayout());
        if (hasStoredCredentials()) {
            preflightStoredCredentials();
        }
    }

    @Override
    protected void onDestroy() {
        worker.shutdownNow();
        super.onDestroy();
    }

    // ---------------------------------------------------------------- UI ----

    private View buildLayout() {
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setGravity(Gravity.CENTER_HORIZONTAL);
        int pad = dp(24);
        content.setPadding(pad, dp(56), pad, dp(32));

        TextView title = new TextView(this);
        title.setText("MIGHTY DOOM REVIVAL");
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setTextColor(COLOR_ACCENT);
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 26);
        title.setGravity(Gravity.CENTER);
        title.setLetterSpacing(0.04f);
        title.setShadowLayer(dp(4), 0, dp(2), COLOR_SHADOW);
        content.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("Entre com o e-mail e a senha da sua conta Revival.");
        subtitle.setTextColor(COLOR_TEXT_MUTED);
        subtitle.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        subtitle.setGravity(Gravity.CENTER);
        subtitle.setPadding(0, dp(10), 0, dp(18));
        content.addView(subtitle);

        LinearLayout pill = new LinearLayout(this);
        pill.setOrientation(LinearLayout.HORIZONTAL);
        pill.setGravity(Gravity.CENTER_VERTICAL);
        pill.setBackground(rounded(COLOR_PILL_FILL, COLOR_FIELD_BORDER, 1, 20));
        pill.setPadding(dp(14), dp(8), dp(14), dp(8));
        TextView dot = new TextView(this);
        dot.setText("●");
        dot.setTextColor(COLOR_OK_DOT);
        dot.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
        dot.setPadding(0, 0, dp(8), 0);
        pill.addView(dot);
        TextView server = new TextView(this);
        server.setText("Servidor: " + portalDomain());
        server.setTextColor(COLOR_ACCENT);
        server.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        server.setTextIsSelectable(true);
        pill.addView(server);
        LinearLayout pillWrap = new LinearLayout(this);
        pillWrap.setGravity(Gravity.CENTER_HORIZONTAL);
        pillWrap.addView(pill);
        pillWrap.addView(spacer(20));
        content.addView(pillWrap, matchWidth());

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackground(rounded(COLOR_PANEL_FILL, COLOR_PANEL_BORDER, 1, 18));
        card.setPadding(dp(18), dp(18), dp(18), dp(18));

        emailField = new EditText(this);
        emailField.setHint("E-mail");
        // contentDescription: o hint de um EditText vazio nem sempre chega ao
        // dump do UIAutomator. Com a descricao o campo e localizavel por nome
        // na verificacao automatizada, sem depender de posicao na tela.
        emailField.setContentDescription("Campo E-mail");
        emailField.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
        card.addView(fieldRow("✉", emailField, null));
        card.addView(spacer(12));

        passwordField = new EditText(this);
        passwordField.setHint("Senha da conta");
        passwordField.setContentDescription("Campo Senha");
        passwordField.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        passwordField.setTransformationMethod(PasswordTransformationMethod.getInstance());

        showPasswordButton = new Button(this);
        showPasswordButton.setText("👁");
        showPasswordButton.setContentDescription("Mostrar senha");
        styleIconToggle(showPasswordButton);
        showPasswordButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { togglePassword(); }
        });
        card.addView(fieldRow("🔒", passwordField, showPasswordButton));
        card.addView(spacer(18));

        loginButton = new Button(this);
        loginButton.setText("ENTRAR");
        loginButton.setAllCaps(true);
        loginButton.setTypeface(Typeface.DEFAULT_BOLD);
        loginButton.setTextColor(Color.WHITE);
        loginButton.setLetterSpacing(0.05f);
        loginButton.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        loginButton.setBackground(gradientButtonBg());
        loginButton.setMinHeight(dp(52));
        loginButton.setPadding(0, 0, 0, 0);
        loginButton.setElevation(dp(3));
        loginButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { onLogin(); }
        });
        card.addView(loginButton, matchWidth());
        content.addView(card, matchWidth());
        content.addView(spacer(16));

        forgotButton = new Button(this);
        forgotButton.setText("ESQUECI MINHA SENHA");
        styleSecondaryButton(forgotButton);
        forgotButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { onForgotPassword(); }
        });
        content.addView(forgotButton, matchWidth());
        content.addView(spacer(10));

        createButton = new Button(this);
        createButton.setText("CRIAR CONTA NO SITE");
        styleSecondaryButton(createButton);
        createButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { openPortal("register"); }
        });
        content.addView(createButton, matchWidth());
        content.addView(spacer(10));

        // So aparece quando existe credencial gravada e o preflight nao pode ser
        // concluido por falta de rede: repetir a verificacao e melhor do que
        // exigir que o jogador redigite a senha por causa de um wi-fi instavel.
        retryButton = new Button(this);
        retryButton.setText("TENTAR NOVAMENTE");
        styleSecondaryButton(retryButton);
        retryButton.setVisibility(View.GONE);
        retryButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { preflightStoredCredentials(); }
        });
        content.addView(retryButton, matchWidth());
        content.addView(spacer(16));

        statusView = new TextView(this);
        statusView.setTextColor(COLOR_TEXT_PRIMARY);
        statusView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        statusView.setBackground(rounded(COLOR_STATUS_FILL, COLOR_STATUS_BORDER, 1, 14));
        statusView.setPadding(dp(14), dp(14), dp(14), dp(14));
        statusView.setTextIsSelectable(true);
        statusView.setVisibility(View.GONE);
        content.addView(statusView, matchWidth());

        ScrollView scroll = new ScrollView(this);
        scroll.addView(content, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#0B0604"));
        Bitmap background = decodeBackground();
        if (background != null) {
            ImageView backdrop = new ImageView(this);
            backdrop.setImageBitmap(background);
            backdrop.setScaleType(ImageView.ScaleType.CENTER_CROP);
            root.addView(backdrop, new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        }
        root.addView(scroll, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        return root;
    }

    /** Linha com icone + campo dentro de uma caixa arredondada; `trailing` (pode
     * ser null) e um botao/icone opcional no fim da linha, como o olho de
     * mostrar senha — evita um botao de largura total só para isso. */
    private LinearLayout fieldRow(String icon, EditText field, View trailing) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setBackground(rounded(COLOR_FIELD_FILL, COLOR_FIELD_BORDER, 1, 12));
        row.setPadding(dp(14), dp(4), dp(10), dp(4));

        TextView iconView = new TextView(this);
        iconView.setText(icon);
        iconView.setTextColor(COLOR_ACCENT);
        iconView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        iconView.setPadding(0, 0, dp(10), 0);
        row.addView(iconView);

        field.setTextColor(COLOR_TEXT_PRIMARY);
        field.setHintTextColor(COLOR_TEXT_MUTED);
        field.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        field.setBackground(null);
        field.setPadding(0, dp(12), 0, dp(12));
        row.addView(field, new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        if (trailing != null) row.addView(trailing);
        return row;
    }

    private void styleSecondaryButton(Button button) {
        button.setAllCaps(true);
        button.setTextColor(COLOR_TEXT_PRIMARY);
        button.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        button.setLetterSpacing(0.03f);
        button.setBackground(rounded(COLOR_PILL_FILL, COLOR_FIELD_BORDER, 1, 12));
        button.setMinHeight(dp(46));
        button.setPadding(dp(12), 0, dp(12), 0);
        button.setElevation(0);
    }

    private void styleIconToggle(Button button) {
        button.setBackground(null);
        button.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        button.setMinWidth(dp(36));
        button.setMinHeight(dp(36));
        button.setPadding(dp(6), dp(6), dp(6), dp(6));
        button.setElevation(0);
    }

    private GradientDrawable rounded(int fillColor, int strokeColor, int strokeDp, int radiusDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fillColor);
        if (strokeColor != 0) drawable.setStroke(dp(strokeDp), strokeColor);
        drawable.setCornerRadius(dp(radiusDp));
        return drawable;
    }

    private GradientDrawable gradientButtonBg() {
        GradientDrawable drawable = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{COLOR_BUTTON_START, COLOR_BUTTON_END});
        drawable.setCornerRadius(dp(14));
        return drawable;
    }

    private View spacer(int heightDp) {
        View view = new View(this);
        view.setLayoutParams(new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(heightDp)));
        return view;
    }

    private LinearLayout.LayoutParams matchWidth() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    /** Decodifica o fundo embutido em base64. Nunca impede o login: sem o
     * bitmap (memoria baixa, decode invalido), a Activity cai no fundo solido
     * definido em `root.setBackgroundColor` e segue funcional. */
    private Bitmap decodeBackground() {
        if (BG_B64.length == 0) return null;  // build sem fundo local: fica no solido
        try {
            StringBuilder base64 = new StringBuilder();
            for (String chunk : BG_B64) base64.append(chunk);
            byte[] bytes = Base64.decode(base64.toString(), Base64.NO_WRAP);
            return BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
        } catch (Exception ignored) {
            return null;
        }
    }

    private int dp(int value) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value,
                getResources().getDisplayMetrics());
    }

    private void togglePassword() {
        boolean oculto = passwordField.getTransformationMethod() != null;
        passwordField.setTransformationMethod(oculto ? null : PasswordTransformationMethod.getInstance());
        // Alterna so o glifo: o botao e um icone compacto ao lado do campo,
        // nao um botao de largura total com rotulo por extenso.
        showPasswordButton.setText(oculto ? "🙈" : "👁");
        showPasswordButton.setContentDescription(oculto ? "Ocultar senha" : "Mostrar senha");
        passwordField.setSelection(passwordField.getText().length());
    }

    /** Bloqueia clique duplo enquanto uma chamada está em voo. */
    private void setBusy(boolean value) {
        busy = value;
        createButton.setEnabled(!value);
        loginButton.setEnabled(!value);
        forgotButton.setEnabled(!value);
        showPasswordButton.setEnabled(!value);
        retryButton.setEnabled(!value);
    }

    private void status(String message) {
        statusView.setText(message);
        statusView.setVisibility(message == null || message.isEmpty() ? View.GONE : View.VISIBLE);
    }

    // ------------------------------------------------------------- fluxo ----

    private String portalBaseUrl() {
        try {
            URL base = new URL(BASE_URL);
            return base.getProtocol() + "://" + base.getAuthority();
        } catch (Exception invalid) {
            return BASE_URL;
        }
    }

    private String portalDomain() {
        try { return new URL(BASE_URL).getHost(); }
        catch (Exception invalid) { return BASE_URL; }
    }

    private void openPortal(String mode) {
        try {
            Intent browser = new Intent(Intent.ACTION_VIEW,
                    Uri.parse(portalBaseUrl() + "/account?mode=" + mode));
            startActivity(browser);
            status("O cadastro é feito em " + portalDomain() + ". Depois, volte e entre aqui.");
        } catch (Exception error) {
            status("Abra " + portalBaseUrl() + "/account no navegador para continuar.");
        }
    }

    private void onLogin() {
        if (busy) return;
        final String email = emailField.getText().toString().trim().toLowerCase();
        final String password = passwordField.getText().toString();
        if (!Patterns.EMAIL_ADDRESS.matcher(email).matches() || password.isEmpty()) {
            status("Informe um e-mail válido e a senha.");
            return;
        }
        setBusy(true);
        status("Entrando…");
        worker.execute(new Runnable() {
            @Override public void run() {
                try {
                    JSONObject body = new JSONObject();
                    body.put("email", email);
                    body.put("password", password);
                    Reply reply = postAccount("/account/login", body);
                    final Credentials creds = Credentials.fromAccount(reply.json, password);
                    // Senha temporária NAO e persistida: ela expira e sera trocada,
                    // e o arquivo local ficaria apontando para uma credencial morta.
                    if (reply.json.optBoolean("temporary_password_used", false)) {
                        final String cookie = reply.cookie;
                        ui.post(new Runnable() {
                            @Override public void run() {
                                setBusy(false);
                                showNewPasswordScreen(creds, cookie);
                            }
                        });
                        return;
                    }
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

    private void onForgotPassword() {
        if (busy) return;
        final String email = emailField.getText().toString().trim().toLowerCase();
        if (!Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
            status("Digite o e-mail da conta para recuperar a senha.");
            return;
        }
        setBusy(true);
        status("Solicitando senha temporária…");
        worker.execute(new Runnable() {
            @Override public void run() {
                try {
                    JSONObject body = new JSONObject();
                    body.put("email", email);
                    postAccount("/account/forgot-password", body);
                    ui.post(new Runnable() {
                        @Override public void run() {
                            setBusy(false);
                            status("Se a conta existir, a senha temporária foi enviada. Confira também o spam.");
                        }
                    });
                } catch (final Exception error) {
                    failOnUi(error);
                }
            }
        });
    }

    /**
     * NEW_PASSWORD_SCREEN — obrigatoria depois de entrar com senha temporaria.
     *
     * A temporaria expira em 30 minutos e deixa de valer assim que o jogador
     * define a definitiva. Persistir a temporaria no `credentials.json` seria
     * fabricar o dead-end que este fluxo existe para fechar, entao a Unity so
     * abre depois de a senha permanente estar valendo no servidor E gravada.
     */
    private void showNewPasswordScreen(final Credentials creds, final String cookie) {
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(24);
        content.setPadding(pad, dp(56), pad, dp(32));

        TextView titulo = new TextView(this);
        titulo.setText("DEFINA SUA SENHA");
        titulo.setTypeface(Typeface.DEFAULT_BOLD);
        titulo.setTextColor(COLOR_ACCENT);
        titulo.setTextSize(TypedValue.COMPLEX_UNIT_SP, 22);
        titulo.setGravity(Gravity.CENTER);
        titulo.setLetterSpacing(0.03f);
        titulo.setShadowLayer(dp(4), 0, dp(2), COLOR_SHADOW);
        content.addView(titulo);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackground(rounded(COLOR_PANEL_FILL, COLOR_PANEL_BORDER, 1, 18));
        card.setPadding(dp(18), dp(18), dp(18), dp(18));

        TextView aviso = new TextView(this);
        aviso.setText("Você entrou com a senha temporária enviada por e-mail. "
                + "Ela expira e é de uso único: escolha agora a senha definitiva "
                + "para continuar entrando no jogo.");
        aviso.setTextColor(COLOR_TEXT_MUTED);
        aviso.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        aviso.setPadding(0, 0, 0, dp(16));
        card.addView(aviso);

        final EditText nova = new EditText(this);
        nova.setHint("Nova senha (mínimo de 8 caracteres)");
        nova.setContentDescription("Campo Nova senha");
        nova.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        nova.setTransformationMethod(PasswordTransformationMethod.getInstance());
        card.addView(fieldRow("🔒", nova, null));
        card.addView(spacer(12));

        final EditText repetida = new EditText(this);
        repetida.setHint("Repita a nova senha");
        repetida.setContentDescription("Campo Repita a nova senha");
        repetida.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        repetida.setTransformationMethod(PasswordTransformationMethod.getInstance());
        card.addView(fieldRow("🔒", repetida, null));
        card.addView(spacer(18));

        final TextView estado = new TextView(this);
        estado.setTextColor(COLOR_TEXT_PRIMARY);
        estado.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        estado.setTextIsSelectable(true);

        final Button salvar = new Button(this);
        salvar.setText("SALVAR SENHA E ENTRAR");
        salvar.setAllCaps(true);
        salvar.setTypeface(Typeface.DEFAULT_BOLD);
        salvar.setTextColor(Color.WHITE);
        salvar.setLetterSpacing(0.04f);
        salvar.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        salvar.setBackground(gradientButtonBg());
        salvar.setMinHeight(dp(52));
        salvar.setPadding(0, 0, 0, 0);
        salvar.setElevation(dp(3));
        salvar.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                final String escolhida = nova.getText().toString();
                if (escolhida.length() < 8) {
                    estado.setText("A senha precisa ter pelo menos 8 caracteres.");
                    return;
                }
                if (!escolhida.equals(repetida.getText().toString())) {
                    estado.setText("As duas senhas não são iguais.");
                    return;
                }
                salvar.setEnabled(false);
                estado.setText("Salvando a nova senha\u2026");
                worker.execute(new Runnable() {
                    @Override public void run() {
                        try {
                            JSONObject body = new JSONObject();
                            body.put("current_password", creds.password);
                            body.put("new_password", escolhida);
                            postAccount("/account/password", body, cookie);
                            saveCredentials(creds.withPassword(escolhida));
                            ui.post(new Runnable() {
                                @Override public void run() {
                                    estado.setText("Senha definida. Abrindo o jogo\u2026");
                                    launchUnity();
                                }
                            });
                        } catch (final Exception error) {
                            ui.post(new Runnable() {
                                @Override public void run() {
                                    salvar.setEnabled(true);
                                    estado.setText(messageFor(error));
                                }
                            });
                        }
                    }
                });
            }
        });
        card.addView(salvar, matchWidth());
        content.addView(card, matchWidth());
        content.addView(spacer(16));
        content.addView(estado, matchWidth());

        ScrollView scroll = new ScrollView(this);
        scroll.addView(content, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#0B0604"));
        Bitmap background = decodeBackground();
        if (background != null) {
            ImageView backdrop = new ImageView(this);
            backdrop.setImageBitmap(background);
            backdrop.setScaleType(ImageView.ScaleType.CENTER_CROP);
            root.addView(backdrop, new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        }
        root.addView(scroll, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);
    }

    private void failOnUi(final Exception error) {
        final String message = messageFor(error);
        ui.post(new Runnable() {
            @Override public void run() {
                setBusy(false);
                status(message);
            }
        });
    }

    /**
     * Mensagem por CLASSE de erro: rede, credencial e servidor sao situacoes
     * diferentes para o jogador. Nunca ecoa segredo nem corpo de resposta.
     *
     * `ApiException.status` e o HTTP das rotas /account/*; `gameCode` e o code
     * do envelope quando o erro veio de uma rota /game/*.
     */
    private String messageFor(Exception error) {
        if (!(error instanceof ApiException)) {
            return "Sem conexão com o servidor Revival. Verifique a rede e tente de novo.";
        }
        ApiException api = (ApiException) error;
        if ("invalid-login".equals(api.error)) return "E-mail ou senha não conferem.";
        if ("smtp-not-configured".equals(api.error)) {
            return "Recuperação por e-mail desativada: o administrador deste servidor não configurou o SMTP. "
                    + "Peça a ele para configurar em " + portalDomain()
                    + ", ou entre com a senha que você cadastrou no site.";
        }
        if ("reset-rate-limited".equals(api.error)) return "Aguarde um minuto antes de pedir outra senha temporária.";
        if ("mail-send-failed".equals(api.error)) return "O servidor não conseguiu enviar o e-mail. Tente de novo mais tarde.";
        if ("password-data-invalid".equals(api.error)) return "Senha recusada pelo servidor: use pelo menos 8 caracteres.";
        if ("session-expired".equals(api.error)) return "A sessão expirou. Entre de novo com o e-mail e a senha temporária.";
        if (api.gameCode == 2101 || api.gameCode == 2102) return "E-mail ou senha não conferem.";
        if (api.gameCode == 2010 || api.gameCode == 2011 || api.gameCode == 2200) {
            return "Versão do cliente incompatível com o servidor Revival.";
        }
        if (api.status == 401 || api.status == 403) return "E-mail ou senha não conferem.";
        if (api.status == 410) return "Este servidor Revival é antigo demais para esta tela. Atualize o servidor.";
        if (api.status >= 500) return "O servidor Revival respondeu com erro. Tente de novo em instantes.";
        return "Não foi possível concluir a operação com o servidor.";
    }

    // --------------------------------------------------------------- HTTP ---

    /** Resposta ja parseada + o cookie de sessao que veio no Set-Cookie. */
    private static final class Reply {
        final JSONObject json;
        final String cookie;
        Reply(JSONObject json, String cookie) {
            this.json = json;
            this.cookie = cookie;
        }
    }

    /**
     * `status` = HTTP das rotas /account/*; `error` = campo `error` do corpo;
     * `gameCode` = `code` do envelope quando o erro veio de uma rota /game/*.
     * Os tres existem porque as duas familias de rota falham de jeitos
     * diferentes e a mensagem para o jogador depende de qual foi.
     */
    private static final class ApiException extends Exception {
        final int status;
        final int gameCode;
        final String error;
        ApiException(int status, int gameCode, String error) {
            super("request failed");
            this.status = status;
            this.gameCode = gameCode;
            this.error = error == null ? "" : error;
        }
    }

    /**
     * Rota /game/*: guard de POST + x-ubu-apiversion + content-type JSON, e
     * envelope { uts, code, ... } com 1000 = sucesso. Usada pelo preflight da
     * credencial gravada — a MESMA chamada que a Unity fara em seguida.
     */
    private JSONObject postGame(String path, JSONObject body) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(BASE_URL + path).openConnection();
        try {
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(TIMEOUT_MS);
            conn.setReadTimeout(TIMEOUT_MS);
            conn.setDoOutput(true);
            conn.setRequestProperty("content-type", "application/json");
            conn.setRequestProperty("x-ubu-apiversion", API_VERSION);
            OutputStream out = conn.getOutputStream();
            out.write(body.toString().getBytes(StandardCharsets.UTF_8));
            out.close();

            int status = conn.getResponseCode();
            InputStream stream = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
            JSONObject json = new JSONObject(readAll(stream));
            int code = json.optInt("code", -1);
            if (status != 200 || code != 1000) throw new ApiException(status, code, "");
            return json;
        } finally {
            conn.disconnect();
        }
    }

    private Reply postAccount(String path, JSONObject body) throws Exception {
        return postAccount(path, body, null);
    }

    /** Rota /account/*: JSON simples com `ok`, e cookie de sessao no header. */
    private Reply postAccount(String path, JSONObject body, String cookie) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(BASE_URL + path).openConnection();
        try {
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(TIMEOUT_MS);
            conn.setReadTimeout(TIMEOUT_MS);
            conn.setDoOutput(true);
            conn.setRequestProperty("content-type", "application/json");
            if (cookie != null && !cookie.isEmpty()) conn.setRequestProperty("cookie", cookie);
            OutputStream out = conn.getOutputStream();
            out.write(body.toString().getBytes(StandardCharsets.UTF_8));
            out.close();

            int status = conn.getResponseCode();
            InputStream stream = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
            JSONObject json = new JSONObject(readAll(stream));
            if (status < 200 || status >= 300 || !json.optBoolean("ok", false)) {
                throw new ApiException(status, -1, json.optString("error", "request-failed"));
            }
            return new Reply(json, sessionCookie(conn));
        } finally {
            conn.disconnect();
        }
    }

    /**
     * So o par nome=valor do Set-Cookie, sem os atributos. E o que o servidor
     * espera de volta em `cookie:` para reconhecer a sessao web na troca de
     * senha. Nunca vai para log, Intent nem Toast.
     */
    private static String sessionCookie(HttpURLConnection conn) {
        for (int i = 0; ; i++) {
            String nome = conn.getHeaderFieldKey(i);
            String valor = conn.getHeaderField(i);
            if (nome == null && valor == null) return null;
            if (nome != null && nome.equalsIgnoreCase("set-cookie") && valor != null) {
                return valor.split(";")[0];
            }
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

        /** O endpoint de conta devolve somente identidade publica; a senha e a
         * digitada pelo jogador e nunca volta no response. */
        static Credentials fromAccount(JSONObject json, String password) throws Exception {
            JSONObject account = json.getJSONObject("account");
            long id = account.getLong("id");
            String device = account.getString("uuid");
            if (id <= 0 || device.length() != 36 || password.isEmpty()) {
                throw new Exception("resposta de conta fora do contrato");
            }
            return new Credentials(id, device, password);
        }

        /** Le o arquivo ja gravado; devolve null se estiver fora do schema. */
        static Credentials fromFile(JSONObject json) {
            long id = json.optLong("user_id", 0);
            String device = json.optString("device_id", "");
            String password = json.optString("password", "");
            if (json.optInt("version", 0) != SAVE_DATA_VERSION
                    || id <= 0 || device.length() != 36 || password.isEmpty()) {
                return null;
            }
            return new Credentials(id, device, password);
        }

        Credentials withPassword(String outra) {
            return new Credentials(userId, deviceId, outra);
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

    /** Le a credencial gravada. Arquivo ausente, vazio ou corrompido = null. */
    private Credentials readStoredCredentials() {
        File file = credentialsFile();
        if (!file.isFile() || file.length() == 0) return null;
        try {
            return Credentials.fromFile(new JSONObject(readAll(new java.io.FileInputStream(file))));
        } catch (Exception broken) {
            // Arquivo corrompido volta para a tela em vez de derrubar o app.
            return null;
        }
    }

    private boolean hasStoredCredentials() {
        return readStoredCredentials() != null;
    }

    private void deleteCredentials() {
        File file = credentialsFile();
        if (file.isFile()) file.delete();
    }

    /**
     * PREFLIGHT — o dead-end da credencial obsoleta morre aqui.
     *
     * O `credentials.json` guarda a SENHA. Se o jogador trocar a senha no site
     * (ou se ele tiver entrado com uma temporaria que ja foi substituida), o
     * arquivo continua com a senha velha. Antes, o boot pulava esta tela,
     * entregava o arquivo para a Unity e o `login-device` batia 403/2101 sem
     * caminho de volta.
     *
     * Agora a Activity faz ELA MESMA o `game/auth/login-device` com o que esta
     * gravado, ANTES de abrir a Unity, e o resultado e deterministico:
     *
     *   - 1000        -> a credencial vale; abre a Unity;
     *   - 403 / 2101  -> a credencial nao vale mais; apaga o arquivo e cai na
     *                    tela de login, com a razao escrita na tela;
     *   - sem rede    -> nao acusa credencial ruim sem ter medido: mantem o
     *                    arquivo, mostra "tentar novamente" e deixa entrar na
     *                    mao se o jogador preferir.
     */
    private void preflightStoredCredentials() {
        final Credentials stored = readStoredCredentials();
        if (stored == null) return;
        setBusy(true);
        retryButton.setVisibility(View.GONE);
        status("Verificando a credencial salva\u2026");
        worker.execute(new Runnable() {
            @Override public void run() {
                try {
                    JSONObject body = new JSONObject();
                    body.put("client_version", CLIENT_VERSION);
                    body.put("user_id", stored.userId);
                    body.put("password", stored.password);
                    postGame("/game/auth/login-device", body);
                    ui.post(new Runnable() {
                        @Override public void run() {
                            status("Credencial confirmada. Abrindo o jogo\u2026");
                            launchUnity();
                        }
                    });
                } catch (final Exception error) {
                    final boolean rejeitada = credentialRejected(error);
                    if (rejeitada) deleteCredentials();
                    ui.post(new Runnable() {
                        @Override public void run() {
                            setBusy(false);
                            if (rejeitada) {
                                retryButton.setVisibility(View.GONE);
                                status("Sua senha mudou desde o último acesso neste aparelho. "
                                        + "Entre de novo com o e-mail e a senha atual.");
                            } else {
                                retryButton.setVisibility(View.VISIBLE);
                                status(messageFor(error)
                                        + " Você também pode entrar com e-mail e senha.");
                            }
                        }
                    });
                }
            }
        });
    }

    /** O servidor RECUSOU a credencial (nao foi rede, nao foi indisponibilidade). */
    private static boolean credentialRejected(Exception error) {
        if (!(error instanceof ApiException)) return false;
        ApiException api = (ApiException) error;
        return api.gameCode == 2101 || api.gameCode == 2102 || api.status == 403;
    }

    /** Gravacao atomica: temporario no MESMO diretorio + rename. */
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
