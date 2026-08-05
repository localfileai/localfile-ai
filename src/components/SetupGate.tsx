import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  getSetupStatus,
  startModelDownload,
  type SetupStatus,
} from '../api/setupApi';

/**
 * 첫 실행 준비 화면 (5주차 배포본).
 *
 * 설치 파일을 받아 실행한 사용자는 터미널을 열지 않는다. 예전에 명령어로
 * 하던 두 가지 — Ollama 설치와 모델 다운로드 — 를 이 화면의 버튼으로 대신한다.
 * 준비가 끝나기 전에는 본 화면을 열지 않는다: 모델 없이 검색·추천을 누르면
 * 503만 보게 되기 때문이다.
 *
 * 준비가 이미 끝난 사용자는 이 화면을 보지 않는다(상태 확인 후 즉시 통과).
 */

type Props = { children: ReactNode };

const POLL_IDLE_MS = 2000;
const POLL_BUSY_MS = 800;

export default function SetupGate({ children }: Props) {
  const [backend, setBackend] = useState<BackendState>({ status: 'starting', detail: '' });
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [installNote, setInstallNote] = useState('');
  const [error, setError] = useState('');
  const [includeFull, setIncludeFull] = useState(false);
  const [busy, setBusy] = useState(false);
  // 준비 없이 화면만 둘러보는 통로. 팀원의 UI 작업과 데모용 —
  // 이 상태에서는 실제 검색·추천이 503으로 실패한다.
  const [bypassed, setBypassed] = useState(false);

  // Electron 메인이 알려 주는 백엔드 상태. 브라우저에서 열면 api가 없으므로
  // 곧바로 통과시키고 아래 상태 폴링이 실제 준비 여부를 판단한다.
  useEffect(() => {
    if (!window.api?.backendStatus) {
      setBackend({ status: 'external', detail: '' });
      return;
    }
    window.api.backendStatus().then(setBackend);
    return window.api.onBackendState(setBackend);
  }, []);

  useEffect(() => {
    if (!window.api?.onOllamaProgress) return;
    return window.api.onOllamaProgress((progress) => setInstallNote(progress.detail));
  }, []);

  const refresh = useCallback(async () => {
    const next = await getSetupStatus();
    if (next) setStatus(next);
    return next;
  }, []);

  // 준비가 끝날 때까지만 상태를 물어본다. 다운로드 중에는 더 자주 —
  // 진행 바가 멈춘 것처럼 보이지 않게.
  useEffect(() => {
    if (status?.ready) return;
    const downloading = status?.download.running ?? false;
    const timer = window.setInterval(refresh, downloading ? POLL_BUSY_MS : POLL_IDLE_MS);
    void refresh();
    return () => window.clearInterval(timer);
  }, [refresh, status?.ready, status?.download.running]);

  const handleInstallOllama = async () => {
    setError('');
    setBusy(true);
    try {
      const result = await window.api.installOllama();
      setInstallNote(result.detail);
    } catch (exception) {
      setError((exception as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleDownload = async () => {
    setError('');
    setBusy(true);
    try {
      const note = await startModelDownload(includeFull);
      if (note) setInstallNote(note);
      await refresh();
    } catch (exception) {
      setError((exception as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // 준비 완료 — 본 화면으로.
  if (status?.ready || bypassed) return <>{children}</>;

  const ollamaMissing = status !== null && !status.ollama.running;
  const download = status?.download;
  const requiredGb = (status?.models ?? [])
    .filter((model) => model.required && !model.present)
    .reduce((sum, model) => sum + model.approx_gb, 0);

  return (
    <div className="flex h-screen items-center justify-center bg-[#F8F9FA] p-8">
      <div className="w-[32rem] rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
        <div className="text-lg font-bold text-gray-800">LocalFile AI 준비</div>
        <p className="mt-1 text-[12px] leading-relaxed text-gray-500">
          처음 한 번만 필요한 과정입니다. 모든 처리는 이 PC 안에서만 이뤄지며,
          문서 내용이 밖으로 나가지 않습니다.
        </p>

        <div className="mt-6 space-y-3">
          <Step
            label="AI 엔진 시작"
            done={backend.status === 'ready' || backend.status === 'external'}
            failed={backend.status === 'failed'}
            detail={backend.status === 'failed' ? backend.detail : backend.detail || ''}
          />
          <Step
            label="Ollama (모델 실행기)"
            done={status?.ollama.running ?? false}
            detail={
              status === null
                ? '확인 중…'
                : status.ollama.running
                  ? '실행 중'
                  : status.ollama.binary_found
                    ? '설치돼 있지만 실행되지 않았습니다. Ollama를 실행해 주세요.'
                    : '설치가 필요합니다.'
            }
          />
          <Step
            label="AI 모델"
            done={(status?.missing_required.length ?? 1) === 0}
            detail={
              status === null
                ? '확인 중…'
                : status.missing_required.length === 0
                  ? '준비 완료'
                  : `${status.missing_required.length}개 필요 (약 ${requiredGb.toFixed(1)}GB)`
            }
          />
        </div>

        {/* 다운로드 진행 바 */}
        {download?.running && (
          <div className="mt-6">
            <div className="flex justify-between text-[11px] text-gray-500">
              <span>{download.model} — {download.phase}</span>
              <span>{download.overall.toFixed(0)}%</span>
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-gray-100">
              <div
                className="h-full rounded-full bg-indigo-500 transition-all duration-300"
                style={{ width: `${download.overall}%` }}
              />
            </div>
            <p className="mt-2 text-[11px] text-gray-400">
              네트워크 속도에 따라 몇 분에서 수십 분이 걸립니다. 창을 닫지 마세요.
            </p>
          </div>
        )}

        {/* 고품질 모델 선택 — 기본은 경량 구성 */}
        {!download?.running && status?.ollama.running && status.missing_required.length > 0 && (
          <label className="mt-6 flex cursor-pointer items-start gap-2 rounded-lg bg-gray-50 p-3">
            <input
              type="checkbox"
              checked={includeFull}
              onChange={(event) => setIncludeFull(event.target.checked)}
              className="mt-0.5"
            />
            <span className="text-[11px] leading-relaxed text-gray-600">
              <b>고품질 모델도 함께 받기</b> (약 4.8GB 추가)
              <br />
              그래픽카드(GPU)가 있는 PC에서 파일명 추천 품질이 좋아집니다.
              나중에 받아도 됩니다.
            </span>
          </label>
        )}

        {(installNote || error || download?.error) && (
          <div
            className={`mt-4 rounded-lg px-3 py-2 text-[11px] leading-relaxed ${
              error || download?.error
                ? 'bg-red-50 text-red-600'
                : 'bg-blue-50 text-blue-700'
            }`}
          >
            {error || download?.error || installNote}
          </div>
        )}

        <div className="mt-6 flex gap-2">
          {ollamaMissing && !status?.ollama.binary_found && (
            <button
              onClick={handleInstallOllama}
              disabled={busy}
              className="flex-1 rounded-lg bg-indigo-600 px-4 py-2.5 text-[12px] font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              Ollama 설치하기
            </button>
          )}

          {status?.ollama.running && status.missing_required.length > 0 && !download?.running && (
            <button
              onClick={handleDownload}
              disabled={busy}
              className="flex-1 rounded-lg bg-indigo-600 px-4 py-2.5 text-[12px] font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              모델 받기 시작
            </button>
          )}

          <button
            onClick={() => void refresh()}
            disabled={busy}
            className="rounded-lg border border-gray-200 px-4 py-2.5 text-[12px] font-bold text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          >
            다시 확인
          </button>
        </div>

        {!download?.running && (
          <button
            onClick={() => setBypassed(true)}
            className="mt-3 w-full text-[11px] text-gray-400 underline underline-offset-2 hover:text-gray-600"
          >
            준비 없이 화면만 둘러보기 (검색·추천은 동작하지 않습니다)
          </button>
        )}
      </div>
    </div>
  );
}

function Step({
  label,
  done,
  failed = false,
  detail,
}: {
  label: string;
  done: boolean;
  failed?: boolean;
  detail: string;
}) {
  const mark = failed ? '✕' : done ? '✓' : '…';
  const tone = failed
    ? 'bg-red-100 text-red-600'
    : done
      ? 'bg-green-100 text-green-600'
      : 'bg-gray-100 text-gray-400';

  return (
    <div className="flex items-start gap-3">
      <div
        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${tone}`}
      >
        {mark}
      </div>
      <div className="min-w-0">
        <div className="text-[12px] font-bold text-gray-700">{label}</div>
        {detail && <div className="text-[11px] text-gray-500">{detail}</div>}
      </div>
    </div>
  );
}
