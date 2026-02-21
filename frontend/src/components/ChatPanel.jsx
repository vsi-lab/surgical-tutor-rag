import React, {useState} from 'react'
import axios from 'axios'
import { API_BASE_URL } from '../config'

export default function ChatPanel({level}){
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  const send = async ()=>{
    if(!query) return
    
    console.log('💬 Sending chat message...')
    console.log('Query:', query)
    console.log('Level:', level)
    
    const userMessage = query
    setMessages(prev=>[...prev, {from:'user', text: userMessage}])
    setQuery('')
    setLoading(true)
    
    const fd = new FormData()
    fd.append('query', userMessage)
    fd.append('level', level)
    
    try{
      console.log('📤 Sending request to backend...')
      const startTime = Date.now()
      const res = await axios.post(`${API_BASE_URL}/chat`, fd)
      const duration = ((Date.now() - startTime) / 1000).toFixed(2)
      console.log(`✅ Response received in ${duration}s:`, res.data)
      setMessages(prev=>[...prev, {from:'bot', text: res.data.answer, contexts: res.data.contexts}])
    }catch(e){
      console.error('❌ Chat failed:', e)
      setMessages(prev=>[...prev, {from:'bot', text: `Error: ${e.response?.data?.detail || e.message || 'could not reach backend'}`}])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl border-2 border-cyan-200 dark:border-cyan-500/30 shadow-2xl dark:shadow-cyan-500/20 rounded-2xl flex flex-col h-full overflow-hidden transition-all duration-300 hover:border-cyan-300 dark:hover:border-cyan-400/40">
      {/* Enhanced Header */}
      <div className="bg-gradient-to-r from-cyan-500 to-blue-600 dark:from-cyan-600 dark:to-blue-700 px-6 py-5 border-b border-cyan-400 dark:border-cyan-500/50">
        <div className="flex items-center gap-4">
          <div className="relative">
            <div className="absolute inset-0 bg-white rounded-xl blur-md opacity-40"></div>
            <div className="relative w-14 h-14 bg-white/20 backdrop-blur-sm rounded-xl flex items-center justify-center text-white shadow-lg border-2 border-white/30">
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
          </div>
          <div className="flex-1">
            <h3 className="text-2xl font-bold text-white drop-shadow-lg">AI Medical Assistant</h3>
            <p className="text-sm text-cyan-50">Surgical education powered by Gemini</p>
          </div>
          <div className="flex items-center gap-2 bg-white/20 backdrop-blur-sm px-4 py-2 rounded-full border border-white/30">
            <div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse shadow-lg shadow-emerald-400/50"></div>
            <span className="text-white font-semibold text-sm">Online</span>
          </div>
        </div>
      </div>

      {/* Chat Messages Area */}
      <div className="flex-1 overflow-auto p-6 bg-gradient-to-b from-slate-50 via-cyan-50/30 to-blue-50/30 dark:from-slate-950/50 dark:via-cyan-950/20 dark:to-blue-950/20 space-y-4">
        {messages.length === 0 && !loading && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-md">
              <div className="relative inline-block mb-6">
                <div className="absolute inset-0 bg-gradient-to-br from-cyan-400 to-blue-500 rounded-full blur-2xl opacity-20 animate-pulse"></div>
                <div className="relative w-24 h-24 bg-gradient-to-br from-cyan-100 to-blue-100 dark:from-cyan-900/30 dark:to-blue-900/30 rounded-full flex items-center justify-center border-4 border-cyan-200 dark:border-cyan-700/50">
                  <svg className="w-12 h-12 text-cyan-600 dark:text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
              </div>
              <h4 className="text-xl font-bold text-gray-800 dark:text-gray-200 mb-3">
                Welcome to Medical AI Assistant
              </h4>
              <p className="text-gray-600 dark:text-gray-400 mb-6">
                Ask me anything about surgical procedures, techniques, instruments, or medical concepts
              </p>
              <div className="grid grid-cols-1 gap-3 text-sm">
                <div className="bg-white dark:bg-slate-800/50 rounded-lg p-3 border-2 border-cyan-100 dark:border-cyan-800/50 text-left">
                  <div className="flex items-start gap-2">
                    <svg className="w-5 h-5 text-cyan-600 dark:text-cyan-400 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                    </svg>
                    <span className="text-gray-700 dark:text-gray-300">"What are the steps for laparoscopic cholecystectomy?"</span>
                  </div>
                </div>
                <div className="bg-white dark:bg-slate-800/50 rounded-lg p-3 border-2 border-cyan-100 dark:border-cyan-800/50 text-left">
                  <div className="flex items-start gap-2">
                    <svg className="w-5 h-5 text-cyan-600 dark:text-cyan-400 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                    </svg>
                    <span className="text-gray-700 dark:text-gray-300">"Explain the anatomy of the biliary tree"</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
        
        {messages.map((m,i)=> (
          <div key={i} className={`flex ${m.from==='user' ? 'justify-end' : 'justify-start'} animate-message-in`}>
            <div className={`max-w-[85%] ${
              m.from==='user' 
                  ? 'bg-gradient-to-br from-cyan-500 to-blue-600 dark:from-cyan-600 dark:to-blue-700 text-white rounded-2xl rounded-tr-sm shadow-lg hover:shadow-xl transition-shadow' 
                  : 'bg-white dark:bg-slate-800/90 text-gray-800 dark:text-slate-100 rounded-2xl rounded-tl-sm shadow-lg border-2 border-cyan-100 dark:border-cyan-700/50 hover:border-cyan-200 dark:hover:border-cyan-600/50 transition-all'
            } p-5`}>
              <div className="whitespace-pre-wrap leading-relaxed">{m.text}</div>
              {m.contexts && m.contexts.length > 0 && (
                <details className="mt-4 text-sm">
                  <summary className="cursor-pointer font-semibold text-cyan-700 dark:text-cyan-400 hover:text-cyan-800 dark:hover:text-cyan-300 transition-colors flex items-center gap-2">
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
                    </svg>
                    View {m.contexts.length} medical reference{m.contexts.length > 1 ? 's' : ''}
                  </summary>
                  <div className="mt-3 space-y-2">
                    {m.contexts.map((c,idx)=> (
                      <div key={idx} className="bg-cyan-50 dark:bg-cyan-900/20 p-3 rounded-lg border-2 border-cyan-200 dark:border-cyan-800/50">
                        <div className="flex items-start justify-between mb-1">
                          <span className="font-semibold text-cyan-900 dark:text-cyan-200">{c.metadata?.title || 'Medical Source'}</span>
                          <span className="text-xs px-2.5 py-1 bg-cyan-200 dark:bg-cyan-800 text-cyan-800 dark:text-cyan-200 rounded-full font-semibold">
                            {(c.score * 100).toFixed(0)}% match
                          </span>
                        </div>
                        <p className="text-xs text-gray-700 dark:text-gray-300 line-clamp-2">{c.metadata?.text}</p>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          </div>
        ))}
        
        {loading && (
          <div className="flex justify-start animate-message-in">
            <div className="bg-white dark:bg-slate-800/90 text-gray-800 dark:text-slate-100 rounded-2xl rounded-tl-sm shadow-lg border-2 border-cyan-100 dark:border-cyan-700/50 p-5 flex items-center gap-3">
              <div className="flex space-x-2">
                <div className="w-2.5 h-2.5 bg-gradient-to-r from-cyan-500 to-blue-600 rounded-full animate-bounce" style={{animationDelay: '0ms'}}></div>
                <div className="w-2.5 h-2.5 bg-gradient-to-r from-cyan-500 to-blue-600 rounded-full animate-bounce" style={{animationDelay: '150ms'}}></div>
                <div className="w-2.5 h-2.5 bg-gradient-to-r from-cyan-500 to-blue-600 rounded-full animate-bounce" style={{animationDelay: '300ms'}}></div>
              </div>
              <span className="text-sm font-medium text-gray-600 dark:text-gray-400">AI is analyzing...</span>
            </div>
          </div>
        )}
      </div>

      {/* Enhanced Input Area */}
      <div className="bg-white/50 dark:bg-slate-800/50 backdrop-blur-sm border-t-2 border-cyan-200 dark:border-cyan-700/50 p-4">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <input 
              className="w-full px-5 py-4 pr-12 border-2 border-cyan-300 dark:border-cyan-700 rounded-xl focus:outline-none focus:border-cyan-500 dark:focus:border-cyan-500 focus:ring-4 focus:ring-cyan-100 dark:focus:ring-cyan-900/30 transition-all duration-200 bg-white dark:bg-slate-900 text-gray-800 dark:text-gray-200 placeholder-gray-500 dark:placeholder-gray-500 font-medium shadow-inner disabled:opacity-50 disabled:cursor-not-allowed" 
              value={query} 
              onChange={e=>setQuery(e.target.value)}
              onKeyPress={e => e.key === 'Enter' && !loading && send()}
              disabled={loading}
              placeholder="Ask about surgical procedures, techniques, instruments..."
            />
            <div className="absolute right-4 top-1/2 transform -translate-y-1/2 pointer-events-none">
              <svg className="w-5 h-5 text-cyan-400 dark:text-cyan-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
              </svg>
            </div>
          </div>
          <button 
            onClick={send}
            disabled={loading || !query}
            className={`px-8 py-4 rounded-xl font-bold shadow-lg transition-all duration-300 transform flex items-center gap-2 ${
              loading || !query
                ? 'bg-gray-300 dark:bg-slate-700 text-gray-500 dark:text-gray-600 cursor-not-allowed' 
                : 'bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white hover:scale-105 hover:shadow-2xl active:scale-95'
            }`}
          >
            {loading ? (
              <>
                <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span>Sending</span>
              </>
            ) : (
              <>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
                <span>Send</span>
              </>
            )}
          </button>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-500 mt-2 text-center">
          Press Enter to send • Powered by Gemini AI
        </p>
      </div>

      <style jsx>{`
        @keyframes messageIn {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        
        .animate-message-in {
          animation: messageIn 0.3s ease-out;
        }
      `}</style>
    </div>
  )
}
