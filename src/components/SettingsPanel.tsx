import { useCallback, useEffect, useState } from 'react';
import {
  getSetupStatus,
  selectModel,
  startModelDownload,
  type SetupStatus,
} from '../api/setupApi';
import { applyTheme, readTheme, type Theme } from '../theme';

/**
 * 설정 — 화면 오른쪽 아래 버튼으로 연다.
 *
 * 두 가지만 담는다: 화면 테마와 AI 모델. 모델은 첫 실행 화면에서 한 번 고르지만,
 * 나중에 GPU를 바꾸거나 품질이 아쉬울 때 바꿀 수 있어야 한다.
 */

/** 모델을 고를 때 도움이 되도록 한 줄 요약. 근거는 3주차 실측(ADR-0002). */
const ONE_LINERS: Record<string, string> = {
  light: '가볍고 빠릅니다. 그래픽카드가 없어도 쓸 만합니다.',
  standard: '더 정확한 파일명을 만듭니다. 그래픽카드가 있을 때 권합니다.',
};

export default function SettingsPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>(() => readTheme());
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const refresh = useCallback(async () => {
    const next = await getSetupStatus();
    if (next) setStatus(next);
  }, []);

  useEffect(() => {
    if (isOpen) void refresh();
  }, [isOpen, refresh]);

  // 모델을 받는 동안에는 진행률을 따라간다.
  useEffect(() => {
    if (!isOpen || !status?.download.running) return;
    const timer = window.setInterval(refresh, 1000);
    return () => window.clearInterval(timer);
  }, [isOpen, status?.download.running, refresh]);

  const handleUse = async (model: string) => {
    setError('');
    setNote('');
    try {
      await selectModel(model);
      setNote('이 모델을 사용하도록 바꿨습니다.');
      await refresh();
    } catch (exception) {
      setError((exception as Error).message);
    }
  };

  const handleDownload = async (model: string) => {
    setError('');
    setNote('');
    setBusy(true);
    try {
      await startModelDownload([model]);
      await refresh();
    } catch (exception) {
      setError((exception as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const generateModels = (status?.models ?? []).filter((model) => model.role === 'generate');
  const download = status?.download;

  return (
    <>
      {/* 오른쪽 아래 고정 버튼 */}
      <button
        onClick={() => setIsOpen((open) => !open)}
        title="설정"
        aria-label="설정"
        className="fixed bottom-5 right-5 z-40 flex h-11 w-11 items-center justify-center rounded-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#16161e] text-gray-500 dark:text-gray-400 shadow-lg transition hover:text-indigo-600 hover:shadow-xl"
      >
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="12" cy="12" r="3.2" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>

      {!isOpen ? null : (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/20"
            onClick={() => setIsOpen(false)}
            aria-hidden="true"
          />
          <div className="fixed bottom-20 right-5 z-50 max-h-[calc(100vh-7rem)] w-[24rem] overflow-y-auto rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#16161e] p-5 shadow-2xl">
            <div className="text-sm font-bold text-gray-800 dark:text-gray-100">설정</div>

            {/* 화면 테마 */}
            <div className="mt-4">
              <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500">화면 테마</div>
              <div className="mt-2 inline-flex rounded-xl border border-gray-200 dark:border-gray-700 p-0.5">
                {(['light', 'dark'] as Theme[]).map((option) => (
                  <button
                    key={option}
                    onClick={() => setTheme(option)}
                    className={`rounded-lg px-4 py-1.5 text-[12px] font-bold transition ${
                      theme === option
                        ? 'bg-indigo-50 dark:bg-indigo-500/20 text-indigo-600'
                        : 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/5'
                    }`}
                  >
                    {option === 'light' ? '밝게' : '어둡게'}
                  </button>
                ))}
              </div>
            </div>

            {/* AI 모델 */}
            <div className="mt-5">
              <div className="flex items-baseline justify-between">
                <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500">
                  파일명 추천 모델
                </div>
                {status && (
                  <div className="text-[10px] text-gray-400 dark:text-gray-500">
                    {status.hardware.summary}
                  </div>
                )}
              </div>

              {status === null ? (
                <div className="mt-2 text-[11px] text-gray-400">불러오는 중…</div>
              ) : (
                <div className="mt-2 space-y-2">
                  {generateModels.map((model) => {
                    const inUse = model.name === status.selected_model && model.present;
                    return (
                      <div
                        key={model.name}
                        className={`rounded-xl border p-3 transition ${
                          inUse
                            ? 'border-indigo-400 bg-indigo-50/60 dark:bg-indigo-500/15'
                            : 'border-gray-200 dark:border-gray-700'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-[12px] font-bold text-gray-800 dark:text-gray-100">
                            {model.label}
                          </span>
                          {model.recommended && (
                            <span className="rounded bg-indigo-100 dark:bg-indigo-500/25 px-1.5 py-0.5 text-[10px] font-bold text-indigo-600">
                              이 PC에 추천
                            </span>
                          )}
                          <span className="ml-auto text-[11px] text-gray-400 dark:text-gray-500">
                            {model.approx_gb}GB
                          </span>
                        </div>

                        {/* 고를 때 도움이 되는 한 줄 */}
                        <p className="mt-1 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
                          {ONE_LINERS[model.tier] ?? model.purpose}
                        </p>
                        <p className="mt-0.5 text-[10px] text-gray-400 dark:text-gray-500">
                          {model.detail}
                        </p>

                        <div className="mt-2">
                          {inUse ? (
                            <span className="text-[11px] font-bold text-indigo-600">
                              사용 중입니다
                            </span>
                          ) : model.present ? (
                            <button
                              onClick={() => void handleUse(model.name)}
                              className="rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-1.5 text-[11px] font-bold text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5"
                            >
                              이 모델 사용
                            </button>
                          ) : (
                            <button
                              onClick={() => void handleDownload(model.name)}
                              disabled={busy || download?.running}
                              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-[11px] font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
                            >
                              내려받기 ({model.approx_gb}GB)
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {download?.running && (
                <div className="mt-3">
                  <div className="flex justify-between text-[11px] text-gray-500 dark:text-gray-400">
                    <span>{download.model}</span>
                    <span>{download.overall.toFixed(0)}%</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-white/10">
                    <div
                      className="h-full rounded-full bg-indigo-500 transition-all duration-300"
                      style={{ width: `${download.overall}%` }}
                    />
                  </div>
                </div>
              )}
            </div>

            {(note || error || download?.error) && (
              <div
                className={`mt-4 rounded-lg px-3 py-2 text-[11px] leading-relaxed ${
                  error || download?.error
                    ? 'bg-red-50 dark:bg-red-500/15 text-red-600'
                    : 'bg-blue-50 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300'
                }`}
              >
                {error || download?.error || note}
              </div>
            )}

            <button
              onClick={() => setIsOpen(false)}
              className="mt-5 w-full rounded-lg border border-gray-200 dark:border-gray-700 px-4 py-2 text-[12px] font-bold text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5"
            >
              닫기
            </button>
          </div>
        </>
      )}
    </>
  );
}
