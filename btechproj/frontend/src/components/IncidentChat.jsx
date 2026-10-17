import { useEffect, useRef, useState } from 'react';
import { MessageCircle, X, Loader2, AlertCircle } from 'lucide-react';
import { askAboutIncident } from '../services/incidentService';

const SUGGESTED = [
  'Why does the system suspect this cause?',
  'Which evidence supports this conclusion?',
  'What other causes are possible?',
  'How do I separate endpoint, local, and dependency latency?',
];

function certaintyLabel(certainty) {
  if (certainty === 'verified') return 'Verified from collected evidence';
  if (certainty === 'procedure') return 'Steps using Jaeger, Prometheus, and collected evidence';
  if (certainty === 'insufficient') return 'Insufficient evidence';
  return 'Hypothesis, not confirmed';
}

export default function IncidentChat({ incidentId, onFocusEvidence }) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const bottomRef = useRef(null);

  useEffect(() => {
    setMessages([]);
    setError('');
  }, [incidentId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [messages, loading]);

  async function send(question) {
    const text = question.trim();
    if (!text || loading || !incidentId) return;
    const history = messages.map((item) => ({ role: item.role, content: item.content }));
    setMessages((current) => [...current, { role: 'user', content: text }]);
    setInput('');
    setError('');
    setLoading(true);
    try {
      const data = await askAboutIncident(incidentId, text, history);
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: data.answer,
          certainty: data.certainty,
          evidence_refs: data.evidence_refs || [],
        },
      ]);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'The assistant could not answer that question.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {!open && (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full bg-[#384959] px-4 py-3 text-sm font-semibold text-white shadow-lg hover:bg-[#2b3844]"
      >
        <MessageCircle className="h-4 w-4" />
        Ask AI
      </button>
      )}
      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-900/20 sm:p-4">
          <section className="relative flex h-[min(80vh,640px)] w-full min-h-0 flex-col overflow-hidden bg-white shadow-2xl sm:max-w-md sm:rounded-xl sm:border sm:border-slate-200">
            <header className="shrink-0 flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-slate-800">Ask AI about this incident</h2>
                <p className="text-[11px] text-slate-500">Answers use this incident's report and telemetry only.</p>
              </div>
              <button type="button" onClick={() => setOpen(false)} className="text-slate-500" aria-label="Close chat">
                <X className="h-4 w-4" />
              </button>
            </header>
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
              {messages.length === 0 && (
                <div className="space-y-2">
                  <p className="text-xs text-slate-500">Suggested questions</p>
                  {SUGGESTED.map((question) => (
                    <button
                      key={question}
                      type="button"
                      onClick={() => send(question)}
                      className="block w-full rounded-lg border border-slate-200 px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-50"
                    >
                      {question}
                    </button>
                  ))}
                </div>
              )}
              {messages.map((message, index) => (
                <div key={index} className={message.role === 'user' ? 'text-right' : ''}>
                  <div className={`inline-block max-w-[90%] whitespace-pre-wrap rounded-lg px-3 py-2 text-xs leading-relaxed ${
                    message.role === 'user' ? 'bg-[#384959] text-white' : 'bg-slate-50 text-slate-800 border border-slate-200'
                  }`}>
                    {message.content}
                  </div>
                  {message.role === 'assistant' && (
                    <div className="mt-1 space-y-1">
                      <p className="text-[10px] uppercase tracking-wide text-slate-400">{certaintyLabel(message.certainty)}</p>
                      {message.evidence_refs?.map((ref) => (
                        <button
                          key={`${ref.source}-${ref.index}`}
                          type="button"
                          onClick={() => onFocusEvidence?.(ref)}
                          className="block text-[11px] font-medium text-[#6A89A7] hover:text-[#384959]"
                        >
                          {ref.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {loading && (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Reading this incident's evidence
                </div>
              )}
              {error && (
                <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-800">
                  <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                  {error}
                </div>
              )}
              <div ref={bottomRef} />
            </div>
            <form
              className="flex shrink-0 gap-2 border-t border-slate-200 p-3"
              onSubmit={(event) => {
                event.preventDefault();
                send(input);
              }}
            >
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Ask about this incident"
                className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-xs"
              />
              <button type="submit" disabled={loading || !input.trim()} className="rounded-lg bg-[#384959] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">
                Send
              </button>
            </form>
          </section>
        </div>
      )}
    </>
  );
}
