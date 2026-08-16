// Configuração do site Mighty DOOM Revival.
//
// Por padrão o site é servido pelo próprio Revival Server (server/public),
// então health/APK/download são resolvidos no MESMO domínio automaticamente.
// Só preencha os campos abaixo se o site rodar em um host diferente do server.
window.MD_CONFIG = {
  // Ex.: "https://doom.seudominio.com" (sem barra final). Vazio = mesmo domínio.
  serverUrl: "",
  // Endpoint de saúde. Vazio = "<serverUrl>/revival/health".
  healthUrl: "",
  // Metadados do APK publicado. Vazio = "<serverUrl>/revival/apk".
  apkInfoUrl: "",
  // Página do projeto (botão GitHub + política legal).
  githubUrl: "https://github.com/testesvibecodeing/mighty-doom-revival"
};

// O aviso legal é carregado separadamente para manter o frontend principal simples.
// Ele não altera o backend; apenas exibe a política de uso/preservação da instância.
const revivalLegalScript = document.createElement('script');
revivalLegalScript.src = 'assets/js/legal-modal.js';
revivalLegalScript.async = false;
document.head.appendChild(revivalLegalScript);
