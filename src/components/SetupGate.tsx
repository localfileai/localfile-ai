import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import {
  getSetupStatus,
  selectModel,
  startModelDownload,
  type SetupStatus,
} from '../api/setupApi';
import { onOpenSetupScreen } from '../setupWindow';

/**
 * 첫 실행 준비 화면 (5주차 배포본, 6주차 개편).
 *
 * 설치 파일을 받아 실행한 사용자는 터미널을 열지 않는다. 예전에 명령어로
 * 하던 두 가지 — Ollama 설치와 모델 다운로드 — 를 이 화면이 대신한다.
 *
 * 6주차 개편의 이유는 남의 PC에서 본 화면 하나다. Ollama는 떠 있는데(v0.32.5)
 * 모델 실행 파일이 빠져 있어 무엇을 눌러도 아무 일이 없었고, 화면이 사용자에게
 * 준 것은 "ollama.com에서 직접 받으세요"라는 안내뿐이었다. 그래서 바꾼 것:
 *
 *   - 버튼을 **하나로** 합쳤다. 그 하나가 Ollama 설치 → (깨졌으면) 재설치 →
 *     모델 다운로드까지 끝까지 이어서 한다.
 *   - 실패해도 링크를 띄우고 끝내지 않는다. 다시 시도할 수 있는 버튼이 남는다.
 *   - 준비가 끝난 뒤에도 설정에서 이 화면을 다시 열 수 있다.
 */

type Props = { children: ReactNode };

const POLL_IDLE_MS = 2000;
const POLL_BUSY_MS = 800;

export default function SetupGate({ children }: Props) {
  const [backend, setBackend] = useState<BackendState>({ status: 'starting', detail: '' });
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [installNote, setInstallNote] = useState('');
  const [installPercent, setInstallPercent] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  // 사용자가 고른 파일명 추천 모델. 비어 있으면 아직 안 골랐다는 뜻이라
  // 상태를 읽은 뒤 추천 모델로 채운다.
  const [chosenModel, setChosenModel] = useState('');
  // 준비 없이 화면만 둘러보는 통로. 팀원의 UI 작업과 데모용 —
  // 이 상태에서는 실제 검색·추천이 503으로 실패한다.
  const [bypassed, setBypassed] = useState(false);
  // 설정에서 "AI 준비 다시 하기"로 연 경우. 준비가 끝나 있어도 화면을 유지한다.
  const [forced, setForced] = useState(false);

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
    return window.api.onOllamaProgress((progress) => {
      setInstallNote(progress.detail);
      setInstallPercent(progress.phase === 'downloading' ? progress.percent : 100);
    });
  }, []);

  useEffect(() => onOpenSetupScreen(() => {
    setForced(true);
    setBypassed(false);
    setError('');
  }), []);

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
    if (status?.ready && !forced) return;
    const downloading = status?.download.running ?? false;
    const timer = window.setInterval(refresh, downloading ? POLL_BUSY_MS : POLL_IDLE_MS);
    void refresh();
    return () => window.clearInterval(timer);
  }, [refresh, status?.ready, status?.download.running, forced]);

  /**
   * 버튼 하나로 끝까지 — Ollama 설치 → 깨졌으면 재설치 → 모델 전부 받기.
   *
   * 예전에는 이 셋이 각각 다른 버튼이었고, 어느 단계에서 막혔는지 사용자가
   * 스스로 판단해야 했다. 그럴 수 있는 사용자였다면 애초에 터미널을 열었을 것이다.
   */
  const runFullSetup = useCallback(async () => {
    setError('');
    setBusy(true);
    try {
      let current = status ?? (await refresh());

      // 1) Ollama가 아예 없거나 꺼져 있으면 설치부터.
      if (window.api?.installOllama && !current?.ollama.running) {
        const result = await window.api.installOllama();
        setInstallNote(result.detail);
        current = await refresh();
      }

      // 2) 응답은 하는데 모델을 못 돌리는 상태 — 설치가 깨졌거나 낡았다.
      //    이때 모델을 더 받아 봐야 똑같이 죽는다. 설치본을 덮어씌우는 수밖에 없다.
      const broken = current?.embed?.kind === 'runtime'
        || current?.download.error_kind === 'runtime';
      if (window.api?.installOllama && broken) {
        setInstallNote('Ollama 설치가 손상돼 다시 설치합니다…');
        const result = await window.api.installOllama({ repair: true });
        setInstallNote(result.detail);
        current = await refresh();
      }

      // 3) 이 PC 구성대로 모델을 받는다. 고른 모델이 있으면 함께 받는다.
      //    이미 받는 중이면 그대로 둔다 — 겹쳐 부르면 409만 돌아온다.
      if (current?.ollama.running && !current.download.running) {
        const note = await startModelDownload(chosenModel ? [chosenModel] : []);
        if (note) setInstallNote(note);
        await refresh();
      } else if (!window.api?.installOllama) {
        setError('Ollama가 실행 중이 아닙니다. Ollama를 실행한 뒤 [다시 확인]을 눌러 주세요.');
      }
    } catch (exception) {
      setError((exception as Error).message);
    } finally {
      setBusy(false);
    }
  }, [status, chosenModel, refresh]);

  // Ollama가 PC에 아예 없으면 버튼을 기다리지 않고 바로 설치를 시작한다.
  // "설치 파일 하나 받아 실행하면 나머지는 알아서"가 이 앱의 약속이다.
  // 모델은 자동으로 받지 않는다 — 수 GB라 사용자가 보고 시작해야 한다.
  const autoInstallTried = useRef(false);
  useEffect(() => {
    if (autoInstallTried.current || busy) return;
    if (!status || status.ollama.running || status.ollama.binary_found) return;
    if (!window.api?.installOllama) return;

    autoInstallTried.current = true;
    void runFullSetup();
  }, [status, busy, runFullSetup]);

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

  // 준비 완료 — 본 화면으로. (설정에서 연 경우에는 닫을 때까지 남는다.)
  if ((status?.ready || bypassed) && !forced) return <>{children}</>;

  const download = status?.download;
  const installing = busy && installPercent > 0 && installPercent < 100;
  // Ollama가 모델을 못 돌리는 상태. 모델을 더 받는 것으로는 해결되지 않는다.
  const runtimeBroken = status?.embed?.kind === 'runtime'
    || download?.error_kind === 'runtime';
  // 모델은 다 받았는데 검색 모델이 안 도는 상태.
  const embedBlocked = Boolean(
    status?.ollama.running && status.missing_required.length === 0 && !status.embed?.usable,
  );
  const generateModels = (status?.models ?? []).filter((model) => model.role === 'generate');
  const embedModel = (status?.models ?? []).find((model) => model.role === 'embed');

  // 이번에 실제로 받아야 하는 용량 — 이 PC 구성 중 아직 없는 것 + 따로 고른 것.
  const pendingNames = new Set(status?.recommendation.pending ?? []);
  if (chosenModel && !status?.models.find((m) => m.name === chosenModel)?.present) {
    pendingNames.add(chosenModel);
  }
  const pendingGb = (status?.models ?? [])
    .filter((model) => pendingNames.has(model.name))
    .reduce((sum, model) => sum + model.approx_gb, 0);

  const actionLabel = runtimeBroken
    ? 'Ollama 다시 설치하고 이어서 준비하기'
    : !status?.ollama.running
      ? 'Ollama부터 설치하고 이어서 준비하기'
      : pendingGb > 0
        ? `한 번에 모두 설치 (약 ${pendingGb.toFixed(1)}GB)`
        : '준비 다시 하기';

  return (
    <div className="flex h-screen items-center justify-center overflow-y-auto bg-[#F8F9FA] dark:bg-[#0d0d13] p-8">
      <div className="my-auto w-[34rem] rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#16161e] p-8 shadow-sm">
        <div className="text-lg font-bold text-gray-800 dark:text-gray-100">LocalFile AI 준비</div>
        <p className="mt-1 text-[12px] leading-relaxed text-gray-500 dark:text-gray-400">
          처음 한 번만 필요한 과정입니다. 버튼 하나로 필요한 것을 전부 설치합니다.
          모든 처리는 이 PC 안에서만 이뤄지며, 문서 내용이 밖으로 나가지 않습니다.
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
            done={(status?.ollama.running ?? false) && !runtimeBroken}
            failed={runtimeBroken}
            detail={
              status === null
                ? '확인 중…'
                : runtimeBroken
                  // 떠 있는 것과 멀쩡한 것은 다르다. 실행 파일이 빠진 설치가 실제로 있었다.
                  ? `실행 중이지만 모델을 돌리지 못합니다${
                      status.ollama.version ? ` (v${status.ollama.version})` : ''
                    } — 설치가 손상됐습니다. 아래 버튼으로 다시 설치합니다.`
                  : status.ollama.running
                    ? `실행 중${status.ollama.version ? ` (v${status.ollama.version})` : ''}`
                    : status.ollama.binary_found
                      ? '설치돼 있지만 실행되지 않았습니다.'
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
                  ? pendingGb > 0
                    ? `필수 모델은 준비 완료 (추가로 약 ${pendingGb.toFixed(1)}GB 더 받습니다)`
                    : '준비 완료'
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
                      {/* 고른 것과 무관하게 함께 받는 모델. 표준 모델이 안 돌 때
                          물러설 곳이 있어야 해서 항상 받는다. */}
                      {model.planned && !model.recommended && !model.present && (
                        <span className="rounded bg-gray-100 dark:bg-white/10 px-1.5 py-0.5 text-[10px] font-bold text-gray-500 dark:text-gray-400">
                          함께 받음
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
                      {/* 모델마다 배포 조건이 다르다. 어디에도 안 적혀 있으면
                          나중에 아무도 모른 채 위반한다 (ADR-0004). */}
                      {model.license && (
                        <>
                          <br />
                          <span className="text-gray-400 dark:text-gray-500">
                            라이선스: {model.license}
                          </span>
                        </>
                      )}
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

        {/* Ollama 설치본 내려받기 진행 바 — 700MB 남짓이라 그냥 두면 멈춘 줄 안다 */}
        {installing && (
          <ProgressBar label="Ollama 설치본" percent={installPercent} />
        )}

        {/* 모델 다운로드 진행 바 */}
        {download?.running && (
          <>
            <ProgressBar
              label={`${download.model} — ${download.phase}`}
              percent={download.overall}
            />
            <p className="mt-2 text-[11px] text-gray-400 dark:text-gray-500">
              네트워크 속도에 따라 몇 분에서 수십 분이 걸립니다. 창을 닫지 마세요.
            </p>
          </>
        )}

        {(installNote || error || download?.error) && (
          <div
            className={`mt-4 rounded-lg px-3 py-2 text-[11px] leading-relaxed ${
              error || download?.error
                ? 'bg-red-50 dark:bg-red-500/15 text-red-600'
                : 'bg-blue-50 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300'
            }`}
          >
            {error || download?.error || installNote}
          </div>
        )}

        <div className="mt-6 flex gap-2">
          {!download?.running && (
            <button
              onClick={() => void runFullSetup()}
              disabled={busy}
              className="flex-1 rounded-lg bg-indigo-600 px-4 py-2.5 text-[12px] font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {busy ? '준비하는 중…' : actionLabel}
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
            onClick={() => (forced ? setForced(false) : setBypassed(true))}
            className="mt-3 w-full text-[11px] text-gray-400 dark:text-gray-500 underline underline-offset-2 hover:text-gray-600"
          >
            {forced
              ? '닫고 앱으로 돌아가기'
              : '준비 없이 화면만 둘러보기 (검색·추천은 동작하지 않습니다)'}
          </button>
        )}
      </div>
    </div>
  );
}

function ProgressBar({ label, percent }: { label: string; percent: number }) {
  return (
    <div className="mt-6">
      <div className="flex justify-between text-[11px] text-gray-500 dark:text-gray-400">
        <span className="truncate">{label}</span>
        <span>{percent.toFixed(0)}%</span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-white/10">
        <div
          className="h-full rounded-full bg-indigo-500 transition-all duration-300"
          style={{ width: `${percent}%` }}
        />
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
