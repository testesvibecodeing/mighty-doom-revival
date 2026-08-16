// Cena Three.js original do Revival.
// Visual técnico/abstrato: rede de nós, conexões e planos. Sem elementos do jogo.
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js'

export function startNetworkScene (canvas) {
  if (!canvas || matchMedia('(prefers-reduced-motion: reduce)').matches) return null

  const renderer = new THREE.WebGLRenderer({
    canvas,
    alpha: true,
    antialias: false,
    powerPreference: 'low-power'
  })
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.45))
  renderer.setSize(innerWidth, innerHeight)
  renderer.setClearColor(0x071018, 0)

  const scene = new THREE.Scene()
  scene.fog = new THREE.FogExp2(0x071018, 0.055)

  const camera = new THREE.PerspectiveCamera(55, innerWidth / innerHeight, 0.1, 80)
  camera.position.set(0, 0, 14)

  const root = new THREE.Group()
  scene.add(root)

  const mobile = innerWidth < 720
  const nodeCount = mobile ? 42 : 82
  const bounds = { x: 18, y: 12, z: 10 }
  const nodePositions = []

  for (let i = 0; i < nodeCount; i++) {
    nodePositions.push(new THREE.Vector3(
      (Math.random() - 0.5) * bounds.x,
      (Math.random() - 0.5) * bounds.y,
      (Math.random() - 0.5) * bounds.z
    ))
  }

  const pointsGeometry = new THREE.BufferGeometry().setFromPoints(nodePositions)
  const pointsMaterial = new THREE.PointsMaterial({
    color: 0x6fe0d0,
    size: mobile ? 0.055 : 0.065,
    transparent: true,
    opacity: 0.5,
    depthWrite: false,
    blending: THREE.AdditiveBlending
  })
  const points = new THREE.Points(pointsGeometry, pointsMaterial)
  root.add(points)

  const segmentPositions = []
  const maxDistance = mobile ? 3.7 : 3.25
  for (let i = 0; i < nodePositions.length; i++) {
    let connected = 0
    for (let j = i + 1; j < nodePositions.length; j++) {
      if (connected >= 3) break
      if (nodePositions[i].distanceTo(nodePositions[j]) <= maxDistance) {
        segmentPositions.push(
          nodePositions[i].x, nodePositions[i].y, nodePositions[i].z,
          nodePositions[j].x, nodePositions[j].y, nodePositions[j].z
        )
        connected += 1
      }
    }
  }

  const linesGeometry = new THREE.BufferGeometry()
  linesGeometry.setAttribute('position', new THREE.Float32BufferAttribute(segmentPositions, 3))
  const linesMaterial = new THREE.LineBasicMaterial({
    color: 0x62cfe0,
    transparent: true,
    opacity: 0.08,
    blending: THREE.AdditiveBlending
  })
  const lines = new THREE.LineSegments(linesGeometry, linesMaterial)
  root.add(lines)

  const accentGeometry = new THREE.BufferGeometry()
  const accentCount = mobile ? 24 : 46
  const accentPositions = new Float32Array(accentCount * 3)
  for (let i = 0; i < accentCount; i++) {
    accentPositions[i * 3] = (Math.random() - 0.5) * 22
    accentPositions[i * 3 + 1] = (Math.random() - 0.5) * 16
    accentPositions[i * 3 + 2] = -4 - Math.random() * 10
  }
  accentGeometry.setAttribute('position', new THREE.BufferAttribute(accentPositions, 3))
  const accentMaterial = new THREE.PointsMaterial({
    color: 0x928dff,
    size: 0.045,
    opacity: 0.35,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending
  })
  const accents = new THREE.Points(accentGeometry, accentMaterial)
  root.add(accents)

  const planeGeometry = new THREE.PlaneGeometry(34, 22, 14, 10)
  const planeMaterial = new THREE.MeshBasicMaterial({
    color: 0x4d7df3,
    wireframe: true,
    transparent: true,
    opacity: 0.025,
    side: THREE.DoubleSide
  })
  const plane = new THREE.Mesh(planeGeometry, planeMaterial)
  plane.rotation.x = Math.PI * 0.54
  plane.position.set(0, -6, -7)
  root.add(plane)

  const rings = new THREE.Group()
  for (let i = 0; i < 3; i++) {
    const geometry = new THREE.TorusGeometry(3.3 + i * 1.8, 0.012, 3, 64)
    const material = new THREE.MeshBasicMaterial({
      color: i === 1 ? 0x928dff : 0x6fe0d0,
      transparent: true,
      opacity: 0.035
    })
    const ring = new THREE.Mesh(geometry, material)
    ring.position.set(i % 2 ? 7 : -7, i * 2 - 1, -7 - i)
    ring.rotation.set(Math.PI * (0.25 + i * 0.08), i * 0.4, i * 0.7)
    rings.add(ring)
  }
  root.add(rings)

  let pointerX = 0
  let pointerY = 0
  let onlinePulse = 0

  addEventListener('pointermove', event => {
    pointerX = (event.clientX / innerWidth - 0.5) * 2
    pointerY = (event.clientY / innerHeight - 0.5) * 2
  }, { passive: true })

  document.addEventListener('revival:online', () => {
    onlinePulse = 1
  })

  const clock = new THREE.Clock()
  let animationId = 0

  function frame () {
    const elapsed = clock.getElapsedTime()
    onlinePulse *= 0.965

    root.rotation.y += (pointerX * 0.035 - root.rotation.y) * 0.015
    root.rotation.x += (-pointerY * 0.022 - root.rotation.x) * 0.015
    root.position.y = Math.sin(elapsed * 0.16) * 0.12

    pointsMaterial.opacity = 0.46 + Math.sin(elapsed * 0.55) * 0.06 + onlinePulse * 0.16
    linesMaterial.opacity = 0.07 + onlinePulse * 0.04
    accents.rotation.z = elapsed * 0.006
    rings.rotation.z = elapsed * 0.01
    plane.position.x = Math.sin(elapsed * 0.08) * 0.4

    renderer.render(scene, camera)
    animationId = requestAnimationFrame(frame)
  }

  frame()

  const onResize = () => {
    camera.aspect = innerWidth / innerHeight
    camera.updateProjectionMatrix()
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.45))
    renderer.setSize(innerWidth, innerHeight)
  }
  addEventListener('resize', onResize, { passive: true })

  return () => {
    cancelAnimationFrame(animationId)
    removeEventListener('resize', onResize)
    pointsGeometry.dispose()
    pointsMaterial.dispose()
    linesGeometry.dispose()
    linesMaterial.dispose()
    accentGeometry.dispose()
    accentMaterial.dispose()
    planeGeometry.dispose()
    planeMaterial.dispose()
    rings.children.forEach(child => {
      child.geometry.dispose()
      child.material.dispose()
    })
    renderer.dispose()
  }
}
