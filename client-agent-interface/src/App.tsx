import AgentInterface from './AgentInterface'

function App() {

  return (
    <div className="w-screen h-screen relative">
      <div className="absolute top-4 left-4 z-10">
        <img
          src={"bloo-logo-white.svg"}
          alt="Bloo"
          className="h-8 w-auto"
        />
      </div>
      <AgentInterface />
    </div>
  )
}

export default App
