// Configuração do site público de uma instância Revival.
//
// O site é servido pelo próprio servidor Revival por padrão.
// Vazio = same-origin. Não há URL nem mecanismo para buscar APK de terceiros.
window.REVIVAL_CONFIG = {
  // Ex.: "https://revival.seudominio.com". Vazio = domínio atual.
  serverUrl: "",

  // Vazio = "<serverUrl>/revival/health".
  healthUrl: "",

  // Metadados do pacote configurado OPCIONALMENTE publicado pelo administrador
  // desta instância. Vazio = "<serverUrl>/revival/apk".
  apkInfoUrl: "",

  // Repositório central de código/documentação.
  githubUrl: "https://github.com/testesvibecodeing/mighty-doom-revival"
};
