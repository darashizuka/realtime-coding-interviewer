// frontend/src/App.jsx
import React, { useState, useEffect, useRef, useCallback } from 'react';
import Editor from "@monaco-editor/react";
import Webcam from "react-webcam";
import io from 'socket.io-client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import hark from 'hark';
import SpeechRecognition, { useSpeechRecognition } from 'react-speech-recognition';
import Setup from './Setup';
import { HARNESS } from './pythonHarness';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5000';
const socket = io(BACKEND_URL);

const SILENCE_LIMIT_SECONDS = 45;

// LeetCode serves problem images from a host that blocks hotlinking, so route
// them through an image proxy.
function MarkdownImage({ src, alt }) {
  return (
    <img
      src={`https://images.weserv.nl/?url=${encodeURIComponent(src)}`}
      alt={alt || ''}
      crossOrigin="anonymous"
      loading="lazy"
      style={{ maxWidth: '100%', borderRadius: '5px', marginTop: '10px' }}
    />
  );
}

function App() {
  const [sessionStarted, setSessionStarted] = useState(false);
  const [config, setConfig] = useState({ difficulty: '', topic: '', persona: '' });
  const [activeQuestion, setActiveQuestion] = useState(null);
  const [code, setCode] = useState("# Waiting for problem...");
  const [status, setStatus] = useState("Connected ✅");
  // What the interviewer last said. TTS alone is easy to miss, and if the
  // browser blocks speech the app looks dead, so mirror every line on screen.
  const [aiLine, setAiLine] = useState(null);   // { text, kind: 'speech' | 'nudge' }

  // SENSORS
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);

  // Sensor state also lives in refs so the silence timer can read current
  // values without re-subscribing to the microphone on every change.
  const lastActiveRef = useRef(Date.now());
  const isSpeakingRef = useRef(false);
  const lastTypeTime = useRef(0);
  const silenceTimerRef = useRef(null);

  const { transcript, resetTranscript, browserSupportsSpeechRecognition } = useSpeechRecognition();

  // PYTHON RUNNER STATE
  const [output, setOutput] = useState(">> Click 'Run Code' to test your solution.\n");
  const [testResults, setTestResults] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  const pyodideRef = useRef(null);
  const webcamRef = useRef(null);

  // WRAP-UP STATE
  const [feedback, setFeedback] = useState(null);
  const [isEnding, setIsEnding] = useState(false);
  const latestResultsRef = useRef(null);

  const markActive = () => { lastActiveRef.current = Date.now(); };

  // --- 1. INITIALIZE PYODIDE ---
  useEffect(() => {
    const loadPy = async () => {
      if (!window.loadPyodide) return;
      try {
        pyodideRef.current = await window.loadPyodide();
        console.log("Pyodide ready");
      } catch (err) {
        console.error("Pyodide failed to load:", err);
      }
    };
    loadPy();
  }, []);

  // --- 2. WEBCAM FRAMES ---
  useEffect(() => {
    if (!sessionStarted) return;
    const interval = setInterval(() => {
      const imageSrc = webcamRef.current?.getScreenshot();
      if (imageSrc) {
        socket.emit('process_frame', { image: imageSrc.split(',')[1] });
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [sessionStarted]);

  // --- 3. SPEECH RECOGNITION ---
  useEffect(() => {
    if (sessionStarted) {
      SpeechRecognition.startListening({ continuous: true, language: 'en-US' });
    }
  }, [sessionStarted]);

  useEffect(() => {
    if (!transcript) return;
    markActive();
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);

    silenceTimerRef.current = setTimeout(() => {
      if (transcript.trim().length > 0) {
        socket.emit('process_user_text', { text: transcript });
        resetTranscript();
      }
    }, 2000);

    return () => clearTimeout(silenceTimerRef.current);
  }, [transcript, resetTranscript]);

  const speakText = useCallback((text) => {
    if (!window.speechSynthesis) return;
    // Stop listening while the AI talks, otherwise the mic transcribes it and
    // feeds the interviewer its own words.
    SpeechRecognition.stopListening();
    setIsAiSpeaking(true);
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    const voices = window.speechSynthesis.getVoices();
    utterance.voice = voices.find(v => v.lang.includes('en-US')) || voices[0];

    const resume = () => {
      setIsAiSpeaking(false);
      markActive();
      SpeechRecognition.startListening({ continuous: true, language: 'en-US' });
    };
    utterance.onend = resume;
    utterance.onerror = resume;
    window.speechSynthesis.speak(utterance);
  }, []);

  // --- 4. SOCKET LISTENERS ---
  useEffect(() => {
    socket.on('ai_text_response', (data) => {
      setAiLine({ text: data.text, kind: 'speech' });
      speakText(data.text);
    });
    socket.on('ai_nudge', (data) => {
      setAiLine({ text: data.message, kind: 'nudge' });
      speakText(data.message);
      markActive();
    });
    socket.on('session_data', (data) => {
      if (!data.question) {
        setOutput(">> No question matched your filters. Try different settings.\n");
        return;
      }
      setActiveQuestion(data.question);
      if (data.question.starter_code) setCode(data.question.starter_code);
    });
    socket.on('interview_feedback', (data) => {
      setFeedback(data.markdown);
      setIsEnding(false);
    });
    socket.on('connect', () => setStatus("Connected ✅"));
    socket.on('disconnect', () => setStatus("Disconnected 🔴"));

    return () => {
      socket.off('ai_text_response');
      socket.off('ai_nudge');
      socket.off('session_data');
      socket.off('interview_feedback');
      socket.off('connect');
      socket.off('disconnect');
    };
  }, [speakText]);

  // --- 5. MICROPHONE + SILENCE WATCHDOG ---
  useEffect(() => {
    if (!sessionStarted) return;
    let speechEvents = null;

    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
      speechEvents = hark(stream, { threshold: -50 });
      speechEvents.on('speaking', () => {
        setIsSpeaking(true);
        isSpeakingRef.current = true;
        markActive();
      });
      speechEvents.on('stopped_speaking', () => {
        setIsSpeaking(false);
        isSpeakingRef.current = false;
      });
    }).catch(console.error);

    const silenceInterval = setInterval(() => {
      if (isSpeakingRef.current) { markActive(); return; }
      const silenceDuration = (Date.now() - lastActiveRef.current) / 1000;
      if (silenceDuration > SILENCE_LIMIT_SECONDS) {
        socket.emit('user_silent', { duration: silenceDuration });
        markActive(); // let the server's cooldown govern repeat nudges
      }
    }, 1000);

    return () => {
      clearInterval(silenceInterval);
      if (speechEvents) speechEvents.stop();
    };
  }, [sessionStarted]);

  // --- HANDLERS ---
  const handleStart = (selectedConfig) => {
    setConfig(selectedConfig);
    setSessionStarted(true);
    socket.emit('start_session', selectedConfig);
    markActive();
  };

  const handleEditorChange = (value) => {
    setCode(value);
    markActive();
    const now = Date.now();
    if (now - lastTypeTime.current > 500) {
      socket.emit('code_update', { code: value });
      socket.emit('user_typing', { timestamp: now });
      lastTypeTime.current = now;
    }
  };

  const handleRunCode = async () => {
    const pyodide = pyodideRef.current;
    if (!pyodide) { setOutput(">> Python runtime is still loading, try again in a moment.\n"); return; }
    if (!activeQuestion) return;

    setIsRunning(true);
    setTestResults(null);
    setOutput(">> Running test cases...\n");

    let meta = {};
    try { meta = JSON.parse(activeQuestion.meta_data || "{}"); } catch { /* ignore */ }

    // Hand everything over as real values rather than interpolating into the
    // Python source, so quotes and backslashes in the editor are harmless.
    pyodide.globals.set("_user_code", code);
    pyodide.globals.set("_cases_json", JSON.stringify(activeQuestion.test_cases || []));
    pyodide.globals.set("_types_json", JSON.stringify(activeQuestion.param_types || []));
    pyodide.globals.set("_return_type", activeQuestion.return_type || "");
    pyodide.globals.set("_func_name", meta.name || "solution");

    try {
      const report = JSON.parse(await pyodide.runPythonAsync(HARNESS));
      setTestResults(report);
      if (report.status === "ok") {
        latestResultsRef.current = { passed: report.passed, total: report.total };
        setOutput(`>> ${report.passed}/${report.total} test cases passed.\n${report.stdout || ""}`);
      } else {
        setOutput(`>> ${report.message}\n${report.stdout || ""}`);
      }
    } catch (err) {
      setOutput(`>> Runner crashed: ${err.message}`);
    } finally {
      setIsRunning(false);
      markActive();
    }
  };

  const handleEndInterview = () => {
    setIsEnding(true);
    SpeechRecognition.stopListening();
    window.speechSynthesis?.cancel();
    socket.emit('end_session', { test_results: latestResultsRef.current });
  };

  if (!sessionStarted) return <Setup onStart={handleStart} />;
  if (!browserSupportsSpeechRecognition) return <span>Use Chrome.</span>;

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh', backgroundColor: '#121212', color: 'white', fontFamily: 'Segoe UI, sans-serif', overflow: 'hidden' }}>

      {/* COLUMN 1: AVATAR & WEBCAM */}
      <div style={{ flex: 1, padding: '10px', display: 'flex', flexDirection: 'column', gap: '10px', borderRight: '1px solid #333', minWidth: '300px' }}>
        <div style={{ flex: 1, background: '#1e1e1e', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
          <h2 style={{ fontSize: '30px' }}>{config.persona}</h2>
          <div style={{ fontSize: '50px', transform: isAiSpeaking ? 'scale(1.2)' : 'scale(1)', transition: '0.2s' }}>
            {isAiSpeaking ? "🗣️" : "🤖"}
          </div>
          <p style={{ color: '#888' }}>AI Interviewer</p>

          {aiLine && (
            <div style={{
              margin: '10px 16px 0', padding: '10px 14px', borderRadius: '8px',
              maxHeight: '30%', overflowY: 'auto', textAlign: 'left', fontSize: '15px',
              lineHeight: 1.45,
              background: aiLine.kind === 'nudge' ? 'rgba(255,152,0,0.12)' : '#252525',
              borderLeft: `4px solid ${aiLine.kind === 'nudge' ? '#ff9800' : '#4caf50'}`,
              color: aiLine.kind === 'nudge' ? '#ffcc80' : '#ddd',
            }}>
              {aiLine.kind === 'nudge' && (
                <div style={{
                  fontSize: '12px', fontWeight: 'bold', letterSpacing: '0.5px',
                  color: '#ff9800', marginBottom: '4px'
                }}>
                  👀 ATTENTION
                </div>
              )}
              {aiLine.text}
            </div>
          )}
        </div>

        <div style={{ flex: 1, background: '#000', borderRadius: '10px', overflow: 'hidden', position: 'relative' }}>
          <Webcam
            ref={webcamRef}
            screenshotFormat="image/jpeg"
            audio={false}
            width="100%"
            height="100%"
            style={{ objectFit: "cover" }}
          />
          <div style={{
            position: 'absolute', bottom: 10, left: 10,
            background: isSpeaking ? '#4caf50' : 'rgba(0,0,0,0.6)',
            color: 'white', padding: '5px 10px', borderRadius: '5px', fontSize: '18px',
            display: 'flex', alignItems: 'center', gap: '5px'
          }}>
            {isSpeaking ? '🎤 Speaking...' : 'You'}
          </div>
        </div>

        <button
          onClick={handleEndInterview}
          disabled={isEnding}
          style={{
            padding: '14px', borderRadius: '8px', border: 'none',
            backgroundColor: isEnding ? '#666' : '#c62828', color: 'white',
            fontSize: '18px', fontWeight: 'bold', cursor: isEnding ? 'wait' : 'pointer'
          }}
        >
          {isEnding ? "Writing feedback..." : "End Interview"}
        </button>
      </div>

      {/* COLUMN 2: QUESTION */}
      <div style={{ flex: 1.5, padding: '25px', overflowY: 'auto', borderRight: '1px solid #333', backgroundColor: '#181818' }}>
        {activeQuestion ? (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '20px' }}>
              <h1 style={{ margin: 0, fontSize: '28px' }}>{activeQuestion.title}</h1>
              <span style={{ backgroundColor: '#ffc01e', color: 'black', padding: '6px 12px', borderRadius: '15px', fontWeight: 'bold', fontSize: '14px' }}>
                {activeQuestion.difficulty}
              </span>
            </div>
            <div className="markdown-body" style={{ color: '#d4d4d4', fontSize: '20px', lineHeight: '1.7' }}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{ img: MarkdownImage }}
              >
                {activeQuestion.markdown_content}
              </ReactMarkdown>
            </div>
          </>
        ) : <h2 style={{ color: '#666' }}>Loading...</h2>}
      </div>

      {/* COLUMN 3: EDITOR + RUNNER */}
      <div style={{ flex: 2, display: 'flex', flexDirection: 'column', borderLeft: '1px solid #333', minWidth: '500px' }}>
        <div style={{ padding: '10px 15px', borderBottom: '1px solid #333', display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1e1e1e' }}>
          <span style={{ fontWeight: 'bold', fontSize: '16px' }}>Python 3</span>
          <div style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
            <span style={{ color: status.includes('Connected') ? '#4caf50' : '#f44336', fontWeight: 'bold', fontSize: '20px' }}>{status}</span>
            <button
              onClick={handleRunCode}
              disabled={isRunning}
              style={{
                backgroundColor: isRunning ? '#666' : '#4caf50',
                color: 'white', border: 'none', padding: '8px 20px', borderRadius: '5px',
                fontSize: '20px', fontWeight: 'bold', cursor: isRunning ? 'wait' : 'pointer'
              }}
            >
              {isRunning ? "Running..." : "▶ Run Code"}
            </button>
          </div>
        </div>

        <div style={{ flex: 2 }}>
          <Editor
            height="100%" defaultLanguage="python" value={code} theme="vs-dark"
            options={{ fontSize: 24, lineHeight: 32, minimap: { enabled: false }, wordWrap: "on", padding: { top: 20 } }}
            onChange={handleEditorChange}
          />
        </div>

        <div style={{
          flex: 1, backgroundColor: '#0d0d0d', borderTop: '1px solid #333',
          padding: '15px', fontFamily: 'Consolas, monospace', fontSize: '18px',
          color: '#e0e0e0', overflowY: 'auto'
        }}>
          <div style={{ color: '#888', marginBottom: '10px', fontSize: '16px', textTransform: 'uppercase' }}>
            Console Output
          </div>
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{output}</pre>

          {testResults?.results?.length > 0 && (
            <div style={{ marginTop: '15px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {testResults.results.map((r, i) => (
                <div key={i} style={{
                  borderLeft: `4px solid ${r.passed ? '#4caf50' : '#f44336'}`,
                  background: '#161616', padding: '10px 12px', borderRadius: '4px'
                }}>
                  <div style={{ fontWeight: 'bold', color: r.passed ? '#4caf50' : '#f44336' }}>
                    {r.passed ? '✓ PASS' : '✗ FAIL'} — case {i + 1}
                  </div>
                  <div style={{ color: '#aaa' }}>input: {JSON.stringify(r.input)}</div>
                  {!r.passed && (
                    <>
                      <div style={{ color: '#aaa' }}>expected: {JSON.stringify(r.expected)}</div>
                      <div style={{ color: '#aaa' }}>
                        actual: {r.error ? <span style={{ color: '#f44336' }}>{r.error}</span> : JSON.stringify(r.actual)}
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* FEEDBACK OVERLAY */}
      {feedback && (
        <div style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.85)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2000, padding: '40px'
        }}>
          <div style={{
            background: '#1e1e1e', borderRadius: '16px', padding: '40px',
            maxWidth: '900px', width: '100%', maxHeight: '85vh', overflowY: 'auto',
            boxShadow: '0 10px 40px rgba(0,0,0,0.6)'
          }}>
            <h1 style={{ marginTop: 0, fontSize: '32px' }}>Interview Feedback</h1>
            <div className="markdown-body" style={{ color: '#d4d4d4', fontSize: '18px', lineHeight: '1.7' }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{feedback}</ReactMarkdown>
            </div>
            <button
              onClick={() => window.location.reload()}
              style={{
                marginTop: '30px', padding: '16px 28px', borderRadius: '8px', border: 'none',
                backgroundColor: '#4caf50', color: 'white', fontSize: '18px',
                fontWeight: 'bold', cursor: 'pointer'
              }}
            >
              Start a New Interview
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
