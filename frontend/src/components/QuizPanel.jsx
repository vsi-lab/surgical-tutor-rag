import React, {useState} from 'react'
import axios from 'axios'
import { API_BASE_URL } from '../config'

export default function QuizPanel({level}){
  const [topic, setTopic] = useState('central line insertion')
  const [quiz, setQuiz] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedAnswers, setSelectedAnswers] = useState({})
  const [submitted, setSubmitted] = useState(false)

  const start = async ()=>{
    console.log('🎯 Starting quiz generation...')
    console.log('Topic:', topic)
    console.log('Level:', level)
    
    setLoading(true)
    setError('')
    setQuiz(null)
    setSelectedAnswers({})
    setSubmitted(false)
    
    const fd = new FormData()
    fd.append('query', topic)
    fd.append('level', level)
    
    try {
      console.log('📤 Sending request to backend...')
      const startTime = Date.now()
      const res = await axios.post(`${API_BASE_URL}/quiz/start`, fd)
      const duration = ((Date.now() - startTime) / 1000).toFixed(2)
      console.log(`✅ Quiz received in ${duration}s:`, res.data)
      console.log('Quiz object:', res.data.quiz)
      console.log('Questions array:', res.data.quiz?.questions)
      console.log('Questions count:', res.data.quiz?.questions?.length)
      
      if (res.data.quiz?.error) {
        setError(res.data.quiz.error)
      } else if (!res.data.quiz?.questions || res.data.quiz.questions.length === 0) {
        setError('No questions generated. Please try again.')
        console.warn('Empty questions array:', res.data.quiz)
      } else {
        setQuiz(res.data.quiz)
      }
    } catch (err) {
      console.error('❌ Quiz generation failed:', err)
      console.error('Error response:', err.response?.data)
      setError(err.response?.data?.detail || err.message || 'Failed to generate quiz')
    } finally {
      setLoading(false)
    }
  }

  const handleAnswerSelect = (questionIndex, answer) => {
    if (!submitted) {
      setSelectedAnswers(prev => ({ ...prev, [questionIndex]: answer }))
    }
  }

  const handleSubmit = () => {
    setSubmitted(true)
    console.log('📝 Quiz submitted! Answers:', selectedAnswers)
  }

  const calculateScore = () => {
    let correct = 0
    quiz.questions.forEach((q, idx) => {
      if (selectedAnswers[idx] === q.correct_answer) correct++
    })
    return correct
  }

  const allQuestionsAnswered = () => {
    if (!quiz || !quiz.questions) return false
    return quiz.questions.every((_, idx) => selectedAnswers[idx] !== undefined)
  }

  return (
    <div className="bg-white/95 dark:bg-slate-900/90 backdrop-blur-xl border-2 border-purple-200 dark:border-purple-500/30 shadow-2xl dark:shadow-purple-500/10 rounded-2xl p-6 hover:shadow-3xl dark:hover:shadow-purple-500/20 hover:border-purple-300 dark:hover:border-purple-400/40 transition-all duration-300 overflow-y-auto flex flex-col">
      <div className="flex items-center gap-3 mb-6">
        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-br from-purple-500 to-pink-600 rounded-xl blur-md opacity-50"></div>
          <div className="relative w-12 h-12 bg-gradient-to-br from-purple-500 to-pink-600 rounded-xl flex items-center justify-center text-white shadow-lg transform hover:rotate-12 transition-transform duration-300">
            <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
            </svg>
          </div>
        </div>
        <div>
          <h3 className="text-xl font-bold text-gray-800 dark:text-gray-100">Practice Quiz</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">Test your knowledge with AI-generated questions</p>
        </div>
      </div>

      {/* Topic Input */}
      <div className="flex gap-3 mb-6">
        <input 
          className="flex-1 px-4 py-3 border-2 border-gray-200 rounded-xl focus:border-purple-500 focus:ring-4 focus:ring-purple-100 outline-none transition-all duration-200 disabled:bg-gray-100"
          placeholder="Enter quiz topic (e.g., laparoscopic cholecystectomy)" 
          value={topic} 
          onChange={e => setTopic(e.target.value)}
          onKeyPress={e => e.key === 'Enter' && !loading && start()}
          disabled={loading}
        />
        <button 
          className={`px-6 py-3 rounded-xl font-semibold transition-all duration-300 transform ${
            loading || !topic.trim()
              ? 'bg-gray-300 text-gray-500 cursor-not-allowed' 
              : 'bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white shadow-lg hover:shadow-xl hover:scale-105'
          }`}
          onClick={start}
          disabled={loading || !topic.trim()}
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Generating...
            </span>
          ) : (
            <span className="flex items-center gap-2">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              Generate Quiz
            </span>
          )}
        </button>
      </div>
      
      {/* Loading State */}
      {loading && (
        <div className="p-6 bg-gradient-to-r from-purple-50 to-pink-50 border-2 border-purple-200 rounded-xl">
          <div className="flex items-center gap-4">
            <div className="relative">
              <div className="w-12 h-12 border-4 border-purple-200 border-t-purple-600 rounded-full animate-spin"></div>
            </div>
            <div>
              <p className="font-semibold text-purple-900">Generating your quiz...</p>
              <p className="text-sm text-purple-700">This may take 30-60 seconds on first run</p>
            </div>
          </div>
        </div>
      )}
      
      {/* Error State */}
      {error && (
        <div className="p-4 bg-red-50 border-2 border-red-200 rounded-xl text-red-800 flex items-start gap-3">
          <svg className="w-6 h-6 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <div>
            <p className="font-semibold">Error</p>
            <p className="text-sm">{error}</p>
          </div>
        </div>
      )}
      
      {/* Quiz Questions */}
      {quiz && quiz.questions && quiz.questions.length > 0 && (
        <div className="space-y-6">
          {/* Progress Header */}
          <div className="flex items-center justify-between p-4 bg-gradient-to-r from-purple-500 to-pink-600 rounded-xl text-white">
            <div>
              <h4 className="font-bold text-lg">
                {submitted ? '🎉 Quiz Complete!' : '📝 Answer All Questions'}
              </h4>
              <p className="text-sm opacity-90">
                {quiz.questions.length} questions • {level} level
              </p>
            </div>
            
            {!submitted ? (
              <div className="text-right">
                <div className="text-2xl font-bold">
                  {Object.keys(selectedAnswers).length}/{quiz.questions.length}
                </div>
                <p className="text-xs opacity-90">Answered</p>
              </div>
            ) : (
              <div className="text-right">
                <div className="text-3xl font-bold">{calculateScore()}/{quiz.questions.length}</div>
                <p className="text-sm opacity-90">
                  {((calculateScore() / quiz.questions.length) * 100).toFixed(0)}% Correct
                </p>
              </div>
            )}
          </div>

          {/* Questions */}
          {quiz.questions.map((q, idx) => {
            const isCorrect = selectedAnswers[idx] === q.correct_answer
            const hasAnswered = selectedAnswers[idx] !== undefined
            
            return (
              <div key={q.id || idx} className={`p-6 rounded-xl border-2 transition-all duration-300 ${
                submitted && hasAnswered
                  ? isCorrect 
                    ? 'bg-emerald-50 border-emerald-300 shadow-lg' 
                    : 'bg-red-50 border-red-300 shadow-lg'
                  : hasAnswered
                  ? 'bg-purple-50 border-purple-300'
                  : 'bg-white border-gray-200 hover:border-purple-200'
              }`}>
                {/* Question Header */}
                <div className="flex items-start gap-3 mb-4">
                  <span className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center font-bold text-white ${
                    submitted && hasAnswered
                      ? isCorrect ? 'bg-emerald-500' : 'bg-red-500'
                      : hasAnswered
                      ? 'bg-purple-500'
                      : 'bg-gray-400'
                  }`}>
                    {submitted && hasAnswered ? (
                      isCorrect ? '✓' : '✗'
                    ) : (
                      idx + 1
                    )}
                  </span>
                  <p className="font-semibold text-gray-800 flex-1 leading-relaxed">{q.question}</p>
                </div>
                
                {/* Answer Options */}
                <div className="space-y-2 mb-4">
                  {q.options && q.options.map((opt, i) => {
                    const optionLetter = String.fromCharCode(65 + i)
                    // Clean option text - remove leading "A) ", "B) ", etc if present
                    const cleanOption = opt.replace(/^[A-D]\)\s*/, '')
                    const isSelected = selectedAnswers[idx] === opt
                    const isCorrectOption = opt === q.correct_answer
                    
                    return (
                      <button
                        key={i}
                        onClick={() => handleAnswerSelect(idx, opt)}
                        disabled={submitted}
                        className={`w-full text-left p-4 rounded-lg border-2 transition-all duration-200 ${
                          submitted
                            ? isCorrectOption
                              ? 'bg-emerald-100 border-emerald-400 font-semibold cursor-default'
                              : isSelected
                              ? 'bg-red-100 border-red-400 cursor-default'
                              : 'bg-gray-50 border-gray-200 cursor-default'
                            : isSelected
                            ? 'bg-purple-100 border-purple-500 font-semibold shadow-md'
                            : 'bg-white border-gray-200 hover:border-purple-300 hover:bg-purple-50 cursor-pointer'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <span className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold transition-all ${
                            submitted
                              ? isCorrectOption
                                ? 'bg-emerald-500 text-white'
                                : isSelected
                                ? 'bg-red-500 text-white'
                                : 'bg-gray-300 text-gray-600'
                              : isSelected
                              ? 'bg-purple-500 text-white'
                              : 'bg-gray-200 text-gray-600'
                          }`}>
                            {optionLetter}
                          </span>
                          <span className="flex-1">{cleanOption}</span>
                          {submitted && isCorrectOption && (
                            <svg className="w-6 h-6 text-emerald-600 animate-bounce" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                            </svg>
                          )}
                          {submitted && isSelected && !isCorrect && (
                            <svg className="w-6 h-6 text-red-600" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                            </svg>
                          )}
                        </div>
                      </button>
                    )
                  })}
                </div>
                
                {/* Explanation (only shown after submission) */}
                {submitted && q.explanation && (
                  <div className="p-4 bg-blue-50 border-2 border-blue-200 rounded-lg animate-fadeIn">
                    <div className="flex items-start gap-2">
                      <svg className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                      </svg>
                      <div>
                        <p className="text-sm font-semibold text-blue-900 mb-1">Explanation:</p>
                        <p className="text-sm text-blue-800 leading-relaxed">{q.explanation}</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })}

          {/* Submit/Results Section */}
          {!submitted ? (
            <div className="text-center">
              <button
                onClick={handleSubmit}
                disabled={!allQuestionsAnswered()}
                className={`px-8 py-4 rounded-xl font-bold text-lg transition-all duration-300 transform ${
                  allQuestionsAnswered()
                    ? 'bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white shadow-xl hover:shadow-2xl hover:scale-105'
                    : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                }`}
              >
                {allQuestionsAnswered() ? (
                  <span className="flex items-center gap-2">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Submit Quiz
                  </span>
                ) : (
                  `Answer ${quiz.questions.length - Object.keys(selectedAnswers).length} More Question${quiz.questions.length - Object.keys(selectedAnswers).length !== 1 ? 's' : ''}`
                )}
              </button>
            </div>
          ) : (
            <div className="text-center p-8 bg-gradient-to-r from-purple-500 to-pink-600 rounded-xl text-white shadow-2xl">
              <div className="mb-4">
                {calculateScore() === quiz.questions.length ? (
                  <div className="text-6xl mb-2">🏆</div>
                ) : calculateScore() >= quiz.questions.length * 0.7 ? (
                  <div className="text-6xl mb-2">🎉</div>
                ) : (
                  <div className="text-6xl mb-2">📚</div>
                )}
              </div>
              <p className="text-5xl font-bold mb-2">{((calculateScore() / quiz.questions.length) * 100).toFixed(0)}%</p>
              <p className="text-xl opacity-90 mb-6">
                You got {calculateScore()} out of {quiz.questions.length} correct
              </p>
              <p className="text-lg opacity-80 mb-6">
                {calculateScore() === quiz.questions.length 
                  ? 'Perfect score! Excellent work! 🌟'
                  : calculateScore() >= quiz.questions.length * 0.7
                  ? 'Great job! Keep up the good work! 💪'
                  : 'Keep learning! Review the explanations above. 📖'}
              </p>
              <button
                onClick={() => {
                  setQuiz(null)
                  setSelectedAnswers({})
                  setSubmitted(false)
                  setTopic('')
                }}
                className="px-6 py-3 bg-white text-purple-600 font-semibold rounded-lg hover:bg-purple-50 transition-colors shadow-lg"
              >
                <span className="flex items-center gap-2">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Take Another Quiz
                </span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
