import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Grid, Text } from "@react-three/drei";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { Point3D } from "./types";

interface PointsCloudProps {
  points: Point3D[];
  cutoffIndex: number;
  autoSpin: boolean;
}

function PointsCloud({ points, cutoffIndex, autoSpin }: PointsCloudProps) {
  const groupRef = useRef<THREE.Group>(null);

  const geometry = useMemo(() => {
    const positions = new Float32Array(points.length * 3);
    const colors = new Float32Array(points.length * 3);
    const colorEarly = new THREE.Color("#1f77b4");
    const colorLate = new THREE.Color("#d62728");
    points.forEach((p, i) => {
      positions[i * 3 + 0] = p.x;
      positions[i * 3 + 1] = p.y;
      positions[i * 3 + 2] = p.z;
      const c = colorEarly.clone().lerp(colorLate, p.t);
      colors[i * 3 + 0] = c.r;
      colors[i * 3 + 1] = c.g;
      colors[i * 3 + 2] = c.b;
    });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    return geo;
  }, [points]);

  useFrame((_state, delta) => {
    if (autoSpin && groupRef.current) {
      groupRef.current.rotation.y += delta * 0.2;
    }
  });

  return (
    <group ref={groupRef}>
      <points geometry={geometry}>
        <pointsMaterial
          size={0.18}
          vertexColors
          sizeAttenuation
          transparent
          opacity={0.95}
        />
      </points>

      <points>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[
              new Float32Array([
                points[cutoffIndex]?.x ?? 0,
                points[cutoffIndex]?.y ?? 0,
                points[cutoffIndex]?.z ?? 0,
              ]),
              3,
            ]}
          />
        </bufferGeometry>
        <pointsMaterial size={0.5} color="#ffe600" sizeAttenuation />
      </points>
    </group>
  );
}

interface AxesProps {
  size?: number;
}

function Axes({ size = 6 }: AxesProps) {
  return (
    <group>
      <mesh position={[size / 2, 0, 0]}>
        <boxGeometry args={[size, 0.02, 0.02]} />
        <meshBasicMaterial color="#888" />
      </mesh>
      <mesh position={[0, size / 2, 0]}>
        <boxGeometry args={[0.02, size, 0.02]} />
        <meshBasicMaterial color="#888" />
      </mesh>
      <mesh position={[0, 0, size / 2]}>
        <boxGeometry args={[0.02, 0.02, size]} />
        <meshBasicMaterial color="#888" />
      </mesh>

      <Text position={[size + 0.3, 0, 0]} fontSize={0.35} color="#bbb">
        Time
      </Text>
      <Text position={[0, size + 0.3, 0]} fontSize={0.35} color="#bbb">
        Price
      </Text>
      <Text position={[0, 0, size + 0.3]} fontSize={0.35} color="#bbb">
        ONI
      </Text>
    </group>
  );
}

interface Scene3DProps {
  points: Point3D[];
  cutoffIndex: number;
  autoSpin: boolean;
}

export default function Scene3D({ points, cutoffIndex, autoSpin }: Scene3DProps) {
  const visiblePoints = points.slice(0, cutoffIndex + 1);
  return (
    <Canvas
      camera={{ position: [8, 6, 10], fov: 50 }}
      style={{ width: "100%", height: "100%", background: "#0d1117" }}
    >
      <ambientLight intensity={0.6} />
      <directionalLight position={[10, 10, 5]} intensity={0.8} />
      <Grid
        args={[20, 20]}
        cellColor="#333"
        sectionColor="#555"
        position={[0, -3, 0]}
      />
      <Axes size={6} />
      <PointsCloud
        points={visiblePoints}
        cutoffIndex={Math.min(cutoffIndex, visiblePoints.length - 1)}
        autoSpin={autoSpin}
      />
      <OrbitControls enablePan enableZoom enableRotate />
    </Canvas>
  );
}
