import React, {useState} from 'react'
import { useTheme } from './ThemeContext'
import ChatPanel from './components/ChatPanel'
import UploadPanel from './components/UploadPanel'
import ImageUploadPanel from './components/ImageUploadPanel'
import VisualQAPanel from './components/VisualQAPanel'
import LevelSelector from './components/LevelSelector'
import QuizPanel from './components/QuizPanel'

export default function App(){
  const { theme, toggleTheme } = useTheme()
  const [level, setLevel] = useState('Novice')
  const [activeTab, setActiveTab] = useState('chat') // 'chat' or 'multimodal'
  const [sidebarOpen, setSidebarOpen] = useState(false)
  
  return (
    <div className="min-h-screen relative overflow-hidden bg-gradient-to-br from-blue-50 via-cyan-50 to-teal-50 dark:from-slate-950 dark:via-cyan-950 dark:to-teal-950 transition-colors duration-500">
      {/* Medical-themed Background Elements */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none">
        <div className="absolute top-20 left-10 w-96 h-96 bg-gradient-to-br from-cyan-400/20 to-blue-400/20 dark:from-cyan-500/10 dark:to-blue-500/10 rounded-full mix-blend-multiply dark:mix-blend-lighten filter blur-3xl opacity-60 animate-blob"></div>
        <div className="absolute top-40 right-10 w-96 h-96 bg-gradient-to-br from-teal-400/20 to-emerald-400/20 dark:from-teal-500/10 dark:to-emerald-500/10 rounded-full mix-blend-multiply dark:mix-blend-lighten filter blur-3xl opacity-60 animate-blob animation-delay-2000"></div>
        <div className="absolute -bottom-8 left-1/2 w-96 h-96 bg-gradient-to-br from-blue-400/20 to-cyan-400/20 dark:from-blue-500/10 dark:to-cyan-500/10 rounded-full mix-blend-multiply dark:mix-blend-lighten filter blur-3xl opacity-60 animate-blob animation-delay-4000"></div>
      </div>

      <div className="relative z-10 flex min-h-screen">
        {/* Main Content Area */}
        <div className="flex-1 flex flex-col overflow-y-auto">
          {/* Top Navigation Bar */}
          <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border-b border-cyan-200 dark:border-cyan-500/30 shadow-lg px-6 py-4">
            <div className="flex items-center justify-between">
              {/* Logo and Title */}
              <div className="flex items-center gap-4">
                <div className="relative">
                  <div className="absolute inset-0 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-xl blur-md opacity-60"></div>
                  <div className="relative w-12 h-12 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-xl flex items-center justify-center text-white shadow-lg">
                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                    </svg>
                  </div>
                </div>
                <div>
                  <h1 className="text-2xl font-bold bg-gradient-to-r from-cyan-600 to-blue-600 dark:from-cyan-400 dark:to-blue-400 bg-clip-text text-transparent">
                    Surgical Education Research Assistant
                  </h1>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Evidence-grounded surgical tutoring prototype</p>
                </div>
              </div>

              {/* Right Side Controls */}
              <div className="flex items-center gap-3">
                {/* Mode Toggle */}
                <div className="flex bg-gray-100 dark:bg-slate-800 rounded-lg p-1">
                  <button
                    onClick={() => setActiveTab('chat')}
                    className={`px-4 py-2 rounded-md text-sm font-semibold transition-all ${
                      activeTab === 'chat'
                        ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-lg'
                        : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                      </svg>
                      Text
                    </span>
                  </button>
                  <button
                    onClick={() => setActiveTab('multimodal')}
                    className={`px-4 py-2 rounded-md text-sm font-semibold transition-all ${
                      activeTab === 'multimodal'
                        ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-lg'
                        : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                      Image
                    </span>
                  </button>
                </div>

                {/* Theme Toggle */}
                <button
                  onClick={toggleTheme}
                  className="p-2.5 bg-white dark:bg-slate-800 rounded-lg shadow-md hover:shadow-lg transition-all border border-gray-200 dark:border-cyan-500/30"
                >
                  {theme === 'light' ? (
                    <svg className="w-5 h-5 text-cyan-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                    </svg>
                  )}
                </button>

                {/* Upload Documents Toggle */}
                <button
                  onClick={() => setSidebarOpen(!sidebarOpen)}
                  className="px-4 py-2.5 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white rounded-lg shadow-md hover:shadow-lg transition-all font-semibold"
                >
                  <span className="flex items-center gap-2">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    Upload Documents
                  </span>
                </button>
              </div>
            </div>

            {/* Educational Warning */}
            <div className="mt-3 flex items-center gap-2 text-xs bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-600/30 rounded-lg px-3 py-2">
              <svg className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <span className="text-amber-800 dark:text-amber-300 font-medium">
                Educational Use Only - Not for Clinical Decision-Making
              </span>
            </div>
          </div>

          {/* Main Content Area */}
          <div className="flex flex-1 p-6 gap-6 min-h-[calc(100vh-180px)]">
            {/* Central AI Assistant Panel */}
            <div className="flex-1 flex flex-col gap-6">
              {/* Chat or Multimodal Panel */}
              <div className="min-h-[500px]">
                {activeTab === 'chat' ? (
                  <ChatPanel level={level} />
                ) : (
                  <div className="h-full grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <ImageUploadPanel />
                    <VisualQAPanel />
                  </div>
                )}
              </div>

              {/* Level Selector - Below Chat */}
              <div className="flex-shrink-0">
                <LevelSelector level={level} setLevel={setLevel} />
              </div>

              {/* Quiz Panel - Below Level Selector */}
              <div className="flex-shrink-0">
                <QuizPanel level={level} />
              </div>
            </div>

            {/* Knowledge Training Sidebar - Only Upload */}
            <div className={`transition-all duration-300 ${sidebarOpen ? 'w-96' : 'w-0'} overflow-hidden flex-shrink-0`}>
              {sidebarOpen && (
                <div className="flex flex-col gap-6 pb-4 animate-slide-right">
                  <UploadPanel />
                </div>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="bg-white/60 dark:bg-slate-900/60 backdrop-blur-xl border-t border-cyan-200 dark:border-cyan-500/30 px-6 py-4">
            <div className="flex items-center justify-between text-sm">
              <div className="text-gray-600 dark:text-gray-400">
                © 2026 Surgical Education Research Assistant • Journal Research Prototype
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></div>
                  <span className="text-emerald-600 dark:text-emerald-400 font-semibold">System Online</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <style jsx>{`
        @keyframes blob {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(30px, -50px) scale(1.15); }
          66% { transform: translate(-20px, 20px) scale(0.9); }
        }
        
        @keyframes slideRight {
          from { opacity: 0; transform: translateX(40px); }
          to { opacity: 1; transform: translateX(0); }
        }
        
        .animate-blob {
          animation: blob 8s infinite ease-in-out;
        }
        
        .animate-slide-right {
          animation: slideRight 0.5s ease-out;
        }
        
        .animation-delay-2000 {
          animation-delay: 2s;
        }
        
        .animation-delay-4000 {
          animation-delay: 4s;
        }
      `}</style>
    </div>
  )
}
