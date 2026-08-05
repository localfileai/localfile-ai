import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import {
  getSetupStatus,
  selectModel,
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
  const [busy, setBusy] = useState(false);
  // 사용자가 고른 파일명 추천 모델. 비어 있으면 아직 안 골랐다는 뜻이라
  // 상태를 읽은 뒤 추천 모델로 채운다.
  const [chosenModel, setChosenModel] = useState('');
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
    if (next) {
      setStatus(next);
      // 첫 진입에서는 이 PC에 권장되는 모델을 미리 골라 둔다.
      setChosenModel((current) => current || next.recommendation.generate_model);
    }
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

  const handleInstallOllama = useCallback(async () => {
    setError('');
    setBusy(true);
    try {
      const result = await window.api.installOllama();
      setInstallNote(result.detail);
      await refresh();
    } catch (exception) {
      setError((exception as Error).message);
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  // Ollama가 없으면 사용자가 버튼을 누르길 기다리지 않고 바로 설치를 시작한다.
  // "설치 파일 하나 받아 실행하면 나머지는 알아서"가 이 앱의 약속이다.
  //
  // 모델은 자동으로 받지 않는다 — 용량이 크고(1.6~4.8GB) PC 사양에 따라
  // 고를 것이 달라지므로, 그건 사용자가 보고 결정해야 한다.
  // 설치 프로그램이 PC에 있는데 꺼져 있기만 한 경우는 건드리지 않는다.
  const autoInstallTried = useRef(false);
  useEffect(() => {
    if (autoInstallTried.current || busy) return;
    if (!status || status.ollama.running || status.ollama.binary_found) return;
    if (!window.api?.installOllama) return;

    autoInstallTried.current = true;
    void handleInstallOllama();
  }, [status, busy, handleInstallOllama]);

  const handleDownload = async () => {
    setError('');
    setBusy(true);
    try {
      const note = await startModelDownload(chosenModel ? [chosenModel] : []);
      if (note) setInstallNote(note);
      await refresh();
    } catch (exception) {
      setError((exception as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // 이미 받아 둔 모델끼리 갈아타는 경우 — 다운로드 없이 설정만 바꾼다.
  const handleSelect = async (model: string) => {
    setChosenModel(model);
    const target = status?.models.find((entry) => entry.name === model);
    if (!target?.present) return;
    try {
      await selectModel(model);
      await refresh();
    } catch (exception) {
      setError((exception as Error).message);
    }
  };

  // 준비 완료 — 본 화면으로.
  if (status?.ready || bypassed) return <>{children}</>;

  const ollamaMissing = status !== null && !status.ollama.running;
  const download = status?.download;
  // 모델은 다 받았는데 검색 모델이 안 도는 상태. 받을 것이 없어 예전에는
  // 버튼이 하나도 안 나왔고, 사용자가 할 수 있는 일이 없었다.
  const embedBlocked = Boolean(
    status?.ollama.running && status.missing_required.length === 0 && !status.embed?.usable,
  );
  const generateModels = (status?.models ?? []).filter((model) => model.role === 'generate');
  const embedModel = (status?.models ?? []).find((model) => model.role === 'embed');

  // 이번에 실제로 받아야 하는 용량 — 이미 있는 모델은 빼고 계산한다.
  const pendingGb =
    (embedModel && !embedModel.present ? embedModel.approx_gb : 0) +
    (generateModels.find((m) => m.name === chosenModel && !m.present)?.approx_gb ?? 0);

  return (
    <div className="flex h-screen items-center justify-center overflow-y-auto bg-[#F8F9FA] dark:bg-[#0d0d13] p-8">
      <div className="my-auto w-[34rem] rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#16161e] p-8 shadow-sm">
        <div className="text-lg font-bold text-gray-800 dark:text-gray-100">LocalFile AI 준비</div>
        <p className="mt-1 text-[12px] leading-relaxed text-gray-500 dark:text-gray-400">
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
                  // 낡은 Ollama는 최신 모델을 받아도 실행하지 못한다.
                  // 문제가 났을 때 제일 먼저 확인해야 하는 값이라 항상 보여 준다.
                  ? `실행 중${status.ollama.version ? ` (v${status.ollama.version})` : ''}`
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
                  : `${status.missing_required.length}개 필요 (약 ${pendingGb.toFixed(1)}GB)`
            }
          />
          {/* 모델을 받았다고 그 PC에서 도는 것은 아니다.
              실제로 한 건 임베딩해 보고 그 결과를 여기 보여 준다 — 예전에는
              이 확인이 없어서, 검색이 죽은 상태로 준비 완료를 통과했다. */}
          <Step
            label="검색 모델 동작 확인"
            done={status?.embed?.usable ?? false}
            failed={Boolean(status?.embed && !status.embed.usable && status.embed.detail)}
            detail={
              status === null
                ? '확인 중…'
                : embedBlocked
                  ? status.embed.detail
                  : status.embed?.usable
                    ? `${status.active_embed_model ?? status.embed.model} 정상`
                    : '모델을 받은 뒤 확인합니다.'
            }
          />
        </div>

        {/* 모델 선택 — 어떤 것을 왜 권하는지 보여 주고 사용자가 고른다 */}
        {status && !download?.running && (
          <div className="mt-6">
            <div className="flex items-baseline justify-between">
              <div className="text-[12px] font-bold text-gray-700 dark:text-gray-200">파일명 추천 모델</div>
              <div className="text-[11px] text-gray-400 dark:text-gray-500">{status.hardware.summary}</div>
            </div>
            <p className="mt-1 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
              {status.recommendation.reason}
            </p>

            <div className="mt-3 space-y-2">
              {generateModels.map((model) => {
                const active = chosenModel === model.name;
                return (
                  <button
                    key={model.name}
                    onClick={() => void handleSelect(model.name)}
                    className={`w-full rounded-xl border p-3 text-left transition ${
                      active
                        ? 'border-indigo-400 bg-indigo-50/60 ring-1 ring-indigo-200'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`h-3.5 w-3.5 shrink-0 rounded-full border-[4px] transition ${
                          active ? 'border-indigo-500' : 'border-gray-200'
                        }`}
                      />
                      <span className="text-[12px] font-bold text-gray-800 dark:text-gray-100">{model.label}</span>
                      {model.recommended && (
                        <span className="rounded bg-indigo-100 dark:bg-indigo-500/25 px-1.5 py-0.5 text-[10px] font-bold text-indigo-600">
                          이 PC에 추천
                        </span>
                      )}
                      {model.present && (
                        <span className="rounded bg-green-100 dark:bg-green-500/20 px-1.5 py-0.5 text-[10px] font-bold text-green-700">
                          받아 둠
                        </span>
                      )}
                      <span className="ml-auto text-[11px] text-gray-400 dark:text-gray-500">
                        {model.approx_gb}GB
                      </span>
                    </div>
                    <div className="mt-1.5 pl-5 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
                      {model.purpose}
                      <br />
                      <span className="text-gray-400 dark:text-gray-500">{model.detail}</span>
                    </div>
                  </button>
                );
              })}
            </div>

            {embedModel && (
              <p className="mt-2 text-[11px] text-gray-400 dark:text-gray-500">
                {embedModel.present
                  ? `검색·분류 엔진(${embedModel.approx_gb}GB)은 준비돼 있습니다.`
                  : `검색·분류 엔진(${embedModel.approx_gb}GB)은 선택과 무관하게 함께 받습니다.`}
              </p>
            )}
          </div>
        )}

        {/* 다운로드 진행 바 */}
        {download?.running && (
          <div className="mt-6">
            <div className="flex justify-between text-[11px] text-gray-500 dark:text-gray-400">
              <span>{download.model} — {download.phase}</span>
              <span>{download.overall.toFixed(0)}%</span>
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-white/10">
              <div
                className="h-full rounded-full bg-indigo-500 transition-all duration-300"
                style={{ width: `${download.overall}%` }}
              />
            </div>
            <p className="mt-2 text-[11px] text-gray-400 dark:text-gray-500">
              네트워크 속도에 따라 몇 분에서 수십 분이 걸립니다. 창을 닫지 마세요.
            </p>
          </div>
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

          {status?.ollama.running
            && (status.missing_required.length > 0 || embedBlocked)
            && !download?.running && (
            <button
              onClick={handleDownload}
              disabled={busy}
              className="flex-1 rounded-lg bg-indigo-600 px-4 py-2.5 text-[12px] font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {embedBlocked
                ? '이 PC에서 되는 검색 모델로 바꾸기'
                : pendingGb > 0
                  ? `선택한 모델 받기 (약 ${pendingGb.toFixed(1)}GB)`
                  : '모델 받기 시작'}
            </button>
          )}

          <button
            onClick={() => void refresh()}
            disabled={busy}
            className="rounded-lg border border-gray-200 dark:border-gray-700 px-4 py-2.5 text-[12px] font-bold text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 disabled:opacity-50"
          >
            다시 확인
          </button>
        </div>

        {!download?.running && (
          <button
            onClick={() => setBypassed(true)}
            className="mt-3 w-full text-[11px] text-gray-400 dark:text-gray-500 underline underline-offset-2 hover:text-gray-600"
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
        <div className="text-[12px] font-bold text-gray-700 dark:text-gray-200">{label}</div>
        {detail && <div className="text-[11px] text-gray-500 dark:text-gray-400">{detail}</div>}
      </div>
    </div>
  );
}
