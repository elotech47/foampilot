import { useState } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import Header from './components/Header'
import FilePanel from './components/FilePanel'
import AgentPanel from './components/AgentPanel'
import ChatPanel from './components/ChatPanel'

const WS_URL = `ws://${window.location.host}/ws`
const DEFAULT_CHAT_WIDTH = 380

export default function App() {
  const [logsOpen, setLogsOpen] = useState(false)
  const [chatWidth, setChatWidth] = useState(DEFAULT_CHAT_WIDTH)

  const { state, startSimulation, stopSimulation, resolveApproval, setAutoApprove, requestFileTree, resetSession } =
    useWebSocket(WS_URL)

  const sessionDone = !state.running && (state.phase === 'complete' || state.phase === 'error' || (state.phase === 'idle' && state.chatMessages.length > 0))

  return (
    <div className="h-screen w-screen flex flex-col bg-[#070b14] text-slate-100 overflow-hidden font-sans select-none">
      <Header
        connected={state.connected}
        running={state.running}
        phase={state.phase}
        sessionId={state.sessionId}
        tokenInfo={state.tokenInfo}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Left: File Explorer */}
        <FilePanel
          fileTree={state.fileTree}
          running={state.running}
          onRefresh={requestFileTree}
        />

        {/* Centre: Agent Process + Logs */}
        <AgentPanel
          events={state.events}
          logsOpen={logsOpen}
          onToggleLogs={() => setLogsOpen(o => !o)}
          running={state.running}
        />

        {/* Right: Chat + Approvals (resizable) */}
        <ChatPanel
          messages={state.chatMessages}
          running={state.running}
          approvalPending={state.approvalPending}
          clarificationPending={state.clarificationPending}
          autoApprove={state.autoApprove}
          sessionDone={sessionDone}
          width={chatWidth}
          onWidthChange={setChatWidth}
          onStart={startSimulation}
          onStop={stopSimulation}
          onNewSession={resetSession}
          onApprove={resolveApproval}
          onSetAutoApprove={setAutoApprove}
        />
      </div>
    </div>
  )
}
