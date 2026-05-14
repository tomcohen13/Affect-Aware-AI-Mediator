import { useMemo } from 'react'
import './SkyBackground.css'

const STAR_COUNT = 120

function seededRandom(seed) {
  const x = Math.sin(seed + 1) * 10000
  return x - Math.floor(x)
}

function Star({ x, y, size, delay, duration, color }) {
  return (
    <div
      className="sky-star"
      style={{
        left: `${x}%`,
        top: `${y}%`,
        width: `${size}px`,
        height: `${size}px`,
        backgroundColor: color,
        boxShadow: `0 0 ${size * 3}px ${size * 1.5}px ${color}`,
        animationDuration: `${duration}s`,
        animationDelay: `${delay}s`,
      }}
    />
  )
}

function Moon() {
  return (
    <div className="sky-moon">
      <div className="sky-moon-crater crater-1" />
      <div className="sky-moon-crater crater-2" />
      <div className="sky-moon-crater crater-3" />
    </div>
  )
}

function Sun() {
  return <div className="sky-sun" />
}

function Cloud({ x, y, scale, delay }) {
  return (
    <div className="sky-cloud" style={{ left: `${x}%`, top: `${y}%`, animationDelay: `${delay}s` }}>
      <div className="sky-cloud-inner" style={{ transform: `scale(${scale})` }}>
        <div className="sky-cloud-body">
          <div className="sky-cloud-puff puff-left" />
          <div className="sky-cloud-puff puff-mid" />
          <div className="sky-cloud-puff puff-right" />
        </div>
      </div>
    </div>
  )
}

export default function SkyBackground({ isDay }) {
  const stars = useMemo(() => (
    Array.from({ length: STAR_COUNT }, (_, i) => {
      const r = (o) => seededRandom(i * 7 + o)
      const sizeRoll = r(2)
      const size = sizeRoll < 0.6  ? 1 + r(3) * 0.8
                 : sizeRoll < 0.85 ? 2 + r(3) * 1.2
                 :                   3 + r(3) * 1.8
      const colorRoll = r(4)
      const color = colorRoll < 0.6 ? 'rgba(255,255,255,0.95)'
                  : colorRoll < 0.8 ? 'rgba(200,220,255,0.9)'
                  :                   'rgba(255,245,200,0.9)'
      return { id: i, x: r(0) * 100, y: r(1) * 88, size, delay: r(5) * 6, duration: 2.5 + r(6) * 4, color }
    })
  ), [])

  const clouds = useMemo(() => [
    { id: 0, x: 3,  y: 11, scale: 1.1,  delay: 0   },
    { id: 1, x: 38, y: 5,  scale: 0.75, delay: 2   },
    { id: 2, x: 61, y: 17, scale: 1.35, delay: 1   },
    { id: 3, x: 79, y: 8,  scale: 0.85, delay: 3.5 },
  ], [])

  return (
    <div className={`sky-bg ${isDay ? 'sky-day' : 'sky-night'}`}>
      {isDay ? (
        <>
          <Sun />
          {clouds.map(c => <Cloud key={c.id} {...c} />)}
        </>
      ) : (
        <>
          <Moon />
          {stars.map(s => <Star key={s.id} {...s} />)}
        </>
      )}
    </div>
  )
}
