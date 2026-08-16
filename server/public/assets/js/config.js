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
  // Página do projeto (botão GitHub).
  githubUrl: "https://github.com/testesvibecodeing/mighty-doom-revival"
};
