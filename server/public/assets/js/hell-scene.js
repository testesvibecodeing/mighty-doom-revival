// hell-scene.js - fundo "inferno" do Mighty DOOM Revival em three.js.
//
// Camadas:
//   1. Pass de shader fullscreen: fumaça/ calor procedural (FBM) que respira,
//      reage ao mouse e recebe "surges" quando o servidor responde.
//   2. Portal do inferno: anel + disco com shader de redemoinho + runas
//      orbitando (InstancedMesh), posicionado atrás do texto do hero.
//   3. Brasas: sistema de partículas 100% GPU (movimento/twinkle no vertex
//      shader), aditivo, com respawn automático - zero trabalho de CPU.
//   4. Parallax de câmera por mouse + scroll.
//
// Desempenho: pixel ratio limitado, menos partículas/runas no mobile,
// FPS-meter que degrada a cena em dois estágios se o aparelho não acompanhar,
// pausa quando a aba fica oculta e desliga total em prefers-reduced-motion.

const THREE = await import('https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.min.js')

const SMOKE_FRAG = `
uniform float uTime;
uniform vec2 uRes;
uniform vec2 uMouse;
uniform float uSurge;
varying vec2 vUv;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453123);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);
  return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),f.x),f.y);}
float fbm(vec2 p){float v=0.0,a=0.5;
  for(int i=0;i<5;i++){v+=a*noise(p);p=p*2.03+vec2(17.3,9.1);a*=0.5;}return v;}
void main(){
  vec2 uv=vUv;
  float aspect=uRes.x/max(uRes.y,1.0);
  vec2 p=uv*vec2(aspect,1.0)*2.4;
  float t=uTime*0.045;
  float q=fbm(p+vec2(t,-t*1.6)+fbm(p*0.65-t)*1.35);
  float r=fbm(p*1.5+vec2(q*2.3,t*0.8)+uSurge*0.6);
  vec3 col=mix(vec3(0.012,0.004,0.003),vec3(0.30,0.055,0.016),smoothstep(0.22,0.9,q));
  col+=vec3(1.0,0.34,0.06)*pow(smoothstep(0.42,1.0,r),2.2)*(0.5+uSurge*0.9);
  col+=vec3(1.0,0.62,0.18)*pow(smoothstep(0.7,1.0,r),3.0)*0.6;
  float md=length((uv-uMouse)*vec2(aspect,1.0));
  col+=vec3(0.9,0.22,0.04)*exp(-md*3.2)*0.14;
  col+=vec3(0.45,0.08,0.015)*pow(1.0-uv.y,3.5)*0.5;
  float vg=smoothstep(1.35,0.3,length(uv-0.5));
  col*=mix(0.5,1.0,vg);
  gl_FragColor=vec4(col,1.0);
}`

const PORTAL_DISC_FRAG = `
uniform float uTime;
varying vec2 vUv;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453123);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);
  return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),f.x),f.y);}
float fbm(vec2 p){float v=0.0,a=0.5;
  for(int i=0;i<4;i++){v+=a*noise(p);p=p*2.1+vec2(11.7,5.3);a*=0.5;}return v;}
void main(){
  vec2 c=vUv*2.0-1.0;
  float r=length(c);
  if(r>1.0)discard;
  float ang=atan(c.y,c.x);
  float sw=fbm(vec2(ang*2.2+uTime*0.35,r*3.5-uTime*0.55));
  vec3 col=vec3(0.015,0.002,0.002);
  col+=vec3(0.75,0.14,0.02)*smoothstep(1.0,0.45,r)*sw*1.5;
  col+=vec3(1.0,0.5,0.1)*pow(smoothstep(0.55,1.0,r),2.5)*0.9;
  float a=smoothstep(1.0,0.88,r);
  gl_FragColor=vec4(col*a*0.95,a);
}`

const PORTAL_RING_FRAG = `
uniform float uTime;
varying vec2 vUv;
void main(){
  float wave=0.5+0.5*sin(vUv.x*25.132+uTime*2.4);
  float pulse=0.75+0.25*sin(uTime*1.6);
  vec3 col=mix(vec3(1.0,0.22,0.02),vec3(1.0,0.78,0.25),wave*0.7)*pulse;
  gl_FragColor=vec4(col,0.9);
}`

const EMBER_VERT = `
uniform float uTime;
uniform float uPixelRatio;
attribute float aSeed;
attribute float aSize;
varying float vTw;
varying float vHeat;
void main(){
  float speed=0.35+fract(aSeed*13.73)*1.15;
  float span=19.0;
  float y=mod(position.y+uTime*speed+aSeed*span,span)-span*0.55;
  float x=position.x+sin(uTime*0.55+aSeed*41.0)*0.4;
  vec4 mv=modelViewMatrix*vec4(x,y,position.z,1.0);
  vTw=0.55+0.45*sin(uTime*(2.0+fract(aSeed*31.7)*3.0)+aSeed*83.0);
  vHeat=fract(aSeed*57.31);
  gl_PointSize=aSize*vTw*uPixelRatio*(11.0/max(0.001,-mv.z));
  gl_Position=projectionMatrix*mv;
}`

const EMBER_FRAG = `
varying float vTw;
varying float vHeat;
void main(){
  vec2 c=gl_PointCoord-0.5;
  float d=length(c);
  float a=smoothstep(0.5,0.0,d);
  a*=a;
  vec3 col=mix(vec3(0.55,0.05,0.008),vec3(1.0,0.72,0.22),vHeat);
  gl_FragColor=vec4(col,a*vTw*0.85);
}`

export function startHellScene (canvas) {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reduced || !canvas) return false

  let renderer
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: false, antialias: false, powerPreference: 'high-performance' })
  } catch {
    return false
  }

  const isSmall = Math.min(innerWidth, innerHeight) < 700
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, isSmall ? 1.5 : 1.75))
  renderer.setSize(innerWidth, innerHeight)
  renderer.autoClear = false

  // --- pass 1: fumaça de fundo (fullscreen) ---
  const smokeScene = new THREE.Scene()
  const smokeCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)
  const smokeUniforms = {
    uTime: { value: 0 },
    uRes: { value: new THREE.Vector2(innerWidth, innerHeight) },
    uMouse: { value: new THREE.Vector2(0.62, 0.4) },
    uSurge: { value: 0 }
  }
  smokeScene.add(new THREE.Mesh(
    new THREE.PlaneGeometry(2, 2),
    new THREE.ShaderMaterial({
      fragmentShader: SMOKE_FRAG,
      uniforms: smokeUniforms,
      depthWrite: false,
      depthTest: false
    })
  ))

  // --- cena principal: portal + brasas ---
  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(58, innerWidth / innerHeight, 0.1, 100)
  camera.position.set(0, 0, 10)

  const portal = new THREE.Group()
  scene.add(portal)

  const discUniforms = { uTime: { value: 0 } }
  portal.add(new THREE.Mesh(
    new THREE.CircleGeometry(2.05, 72),
    new THREE.ShaderMaterial({
      fragmentShader: PORTAL_DISC_FRAG,
      uniforms: discUniforms,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending
    })
  ))

  const ringUniforms = { uTime: { value: 0 } }
  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(2.18, 0.055, 12, 128),
    new THREE.ShaderMaterial({
      fragmentShader: PORTAL_RING_FRAG,
      uniforms: ringUniforms,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending
    })
  )
  portal.add(ring)

  const runes = new THREE.Group()
  const runeCount = isSmall ? 0 : 14
  if (runeCount > 0) {
    const runeGeo = new THREE.OctahedronGeometry(0.085)
    const runeMat = new THREE.MeshBasicMaterial({ color: 0xff7a1e })
    const runeMesh = new THREE.InstancedMesh(runeGeo, runeMat, runeCount)
    const dummy = new THREE.Object3D()
    for (let i = 0; i < runeCount; i++) {
      const a = (i / runeCount) * Math.PI * 2
      dummy.position.set(Math.cos(a) * 2.62, Math.sin(a) * 2.62, 0)
      dummy.rotation.set(a, a * 1.7, 0)
      dummy.updateMatrix()
      runeMesh.setMatrixAt(i, dummy.matrix)
    }
    runes.add(runeMesh)
    portal.add(runes)
  }

  const placePortal = () => {
    if (isSmall) {
      portal.position.set(0, 1.15, -3.2)
      portal.scale.setScalar(0.62)
    } else {
      portal.position.set(4.05, -0.2, -1.6)
      portal.scale.setScalar(1)
    }
  }
  placePortal()

  // --- brasas (partículas GPU) ---
  const emberCount = isSmall ? 620 : 1500
  const positions = new Float32Array(emberCount * 3)
  const seeds = new Float32Array(emberCount)
  const sizes = new Float32Array(emberCount)
  for (let i = 0; i < emberCount; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 26
    positions[i * 3 + 1] = Math.random() * 19
    positions[i * 3 + 2] = -6 + Math.random() * 9
    seeds[i] = Math.random()
    sizes[i] = 1.6 + Math.random() * 3.4
  }
  const emberGeo = new THREE.BufferGeometry()
  emberGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  emberGeo.setAttribute('aSeed', new THREE.BufferAttribute(seeds, 1))
  emberGeo.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1))
  const emberUniforms = { uTime: { value: 0 }, uPixelRatio: { value: renderer.getPixelRatio() } }
  const embers = new THREE.Points(emberGeo, new THREE.ShaderMaterial({
    vertexShader: EMBER_VERT,
    fragmentShader: EMBER_FRAG,
    uniforms: emberUniforms,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending
  }))
  scene.add(embers)

  // --- interação ---
  let mx = 0
  let my = 0
  const onPointer = e => {
    mx = (e.clientX / innerWidth - 0.5) * 2
    my = (e.clientY / innerHeight - 0.5) * 2
    smokeUniforms.uMouse.value.set(e.clientX / innerWidth, 1 - e.clientY / innerHeight)
  }
  addEventListener('pointermove', onPointer, { passive: true })

  let scrollYNow = 0
  addEventListener('scroll', () => { scrollYNow = window.scrollY }, { passive: true })

  addEventListener('resize', () => {
    renderer.setSize(innerWidth, innerHeight)
    smokeUniforms.uRes.value.set(innerWidth, innerHeight)
    camera.aspect = innerWidth / innerHeight
    camera.updateProjectionMatrix()
  })

  // O app dispara "revival:online" a cada health check bem-sucedido: o portal
  // e a fumaça dão uma respirada mais forte.
  let surge = 0
  document.addEventListener('revival:online', () => { surge = 1 })

  // --- loop com degradação adaptativa de qualidade ---
  const clock = new THREE.Clock()
  let frames = 0
  let badFrames = 0
  let quality = 2 // 2 = tudo, 1 = sem runas + dpr menor, 0 = para o loop
  let lastFrame = performance.now()

  function degrade () {
    if (quality === 2) {
      quality = 1
      runes.visible = false
      renderer.setPixelRatio(1)
      renderer.setSize(innerWidth, innerHeight)
      emberUniforms.uPixelRatio.value = 1
    } else if (quality === 1) {
      quality = 0
    }
  }

  function frame () {
    if (quality === 0) return
    requestAnimationFrame(frame)
    if (document.hidden) return

    const now = performance.now()
    const dtFrame = now - lastFrame
    lastFrame = now

    // FPS-meter: considera ruim qualquer frame acima de ~34 ms (sob 30 fps).
    if (dtFrame > 34) badFrames += 1
    frames += 1
    if (frames % 90 === 0) {
      if (badFrames > 30) degrade()
      badFrames = 0
    }

    const t = clock.getElapsedTime()

    surge *= 0.965
    smokeUniforms.uTime.value = t
    smokeUniforms.uSurge.value = surge
    discUniforms.uTime.value = t
    ringUniforms.uTime.value = t
    emberUniforms.uTime.value = t

    ring.rotation.z = t * 0.12
    runes.rotation.z = -t * 0.09
    const pulse = 1 + Math.sin(t * 1.35) * 0.035 + surge * 0.1
    portal.scale.setScalar((isSmall ? 0.62 : 1) * pulse)
    embers.rotation.z = Math.sin(t * 0.05) * 0.03

    camera.position.x += (mx * 0.55 - camera.position.x) * 0.04
    camera.position.y += (-my * 0.38 - scrollYNow * 0.0016 - camera.position.y) * 0.04
    camera.lookAt(0, -scrollYNow * 0.0016, -2)

    renderer.clear()
    renderer.render(smokeScene, smokeCam)
    renderer.render(scene, camera)
  }
  frame()
  return true
}
