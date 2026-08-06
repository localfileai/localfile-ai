import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import {
  getSetupStatus,
  selectModel,
  startModelDownload,
  type SetupStatus,
} from '../api/setupApi';
import { onOpenSetupScreen } from '../setupWindow';

/**
 * 첫 실행 준비 화면 (5주차 배포본, 6주차 전면 개편).
 *
 * 원칙 하나로 정리된다: **처음 사용자는 이 앱의 구조를 모른다.**
 *
 *   - 사용자가 누를 버튼이 없다. 준비가 안 된 채 앱이 뜨면 전 과정(실행 환경
 *     설치 → 모델 다운로드 → 동작 확인)이 알아서 순서대로 돈다. 화면은
 *     단계 목록(진행 중인 단계는 스피너)과 진행 바만 보여 준다.
 *   - 버튼은 실패했을 때의 [다시 시도] 하나뿐이다.
 *   - 내부 구성 요소의 이름(Ollama 같은 것)을 화면에 쓰지 않는다. 어떤 스택을
 *     썼는지는 사용자가 알 필요 없는 정보다. 화면에는 "무엇을 하고 있는지"만
 *     사용자의 말로 적는다.
 *   - 모델 선택 카드는 설정에서 이 화면을 다시 열었을 때만 보인다. 첫 설치는
 *     PC 사양에 맞는 구성이 자동으로 선택된다.
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
  // 설정에서 "AI 준비 다시 하기"로 연 경우. 준비가 끝나 있어도 화면을 유지하고,
  // 이때만 모델 선택 카드와 수동 버튼이 보인다.
  const [forced, setForced] = useState(false);
  // 실행 환경(모델 실행기)이 올라오기를 기다리는 중. 자동 설치가 창을 띄웠거나
  // 서비스가 아직 안 뜬 상태다. 올라오는 순간 아래 효과가 다음 단계로 잇는다.
  const [waitingForRuntime, setWaitingForRuntime] = useState(false);
  // 백엔드(server.exe)가 죽어 상태를 못 읽는 상태.
  const [backendUnreachable, setBackendUnreachable] = useState(false);

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

  // 백엔드가 아직 뜨는 중인지 폴링 실패 판정에서 알아야 한다. state를 그대로
  // 읽으면 콜백이 옛 값을 붙잡으므로 ref로 비춰 둔다.
  const backendUp = useRef(false);
  backendUp.current = backend.status === 'ready' || backend.status === 'external';

  const missedPolls = useRef(0);
  const refresh = useCallback(async () => {
    const next = await getSetupStatus();
    if (next) {
      missedPolls.current = 0;
      setBackendUnreachable(false);
      setStatus(next);
      // 첫 진입에서는 이 PC에 권장되는 모델을 미리 골라 둔다.
      setChosenModel((current) => current || next.recommendation.generate_model);
    } else if (backendUp.current) {
      // 백엔드가 떠 있다고 했는데 연달아 응답이 없으면 죽은 것이다. 그때는
      // 화면이 멀쩡해 보이는 채로 굳으므로 반드시 말해 줘야 한다.
      // (아직 시작 중일 때의 무응답은 정상이라 세지 않는다 — 새 PC에서
      //  server.exe 첫 기동은 몇 초 이상 걸리고, 그걸 오류로 띄우면 오탐이다.)
      missedPolls.current += 1;
      if (missedPolls.current >= 3) setBackendUnreachable(true);
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
   * 전 과정을 순서대로 — 실행 환경 설치 → 깨졌으면 재설치 → 모델 전부 받기.
   * 사용자가 부르는 것이 아니라 앱이 스스로 부른다. 버튼은 실패 후 재시도용이다.
   */
  const runFullSetup = useCallback(async () => {
    setError('');
    setInstallPercent(0);   // 지난 시도의 진행률이 남아 잘못 보이지 않게
    setBusy(true);
    try {
      // refresh()는 백엔드가 잠깐 응답을 안 하면 null을 준다. 그걸 그대로
      // 받아 넣으면 이후 `current?.…`가 전부 거짓이 되어, 오류도 진행도 없이
      // 조용히 끝난다. 실제로 그렇게 굳은 화면을 배포에서 겪었다.
      let current = status ?? (await refresh());

      // 1) 실행 환경이 아예 없거나 꺼져 있으면 설치부터.
      if (window.api?.installOllama && !current?.ollama.running) {
        const result = await window.api.installOllama();
        setInstallNote(result.detail);
        current = (await refresh()) ?? current;

        // 아직 안 보이면 기다린다 — 설치 창이 떠 있거나 서비스가 뜨는 중이다.
        // 폴링이 발견하는 순간 아래 효과가 다음 단계로 잇는다.
        if (!current?.ollama.running) {
          setWaitingForRuntime(true);
          return;
        }
      }

      // 2) 응답은 하는데 모델을 못 돌리는 상태 — 설치가 깨졌거나 낡았다.
      //    이때 모델을 더 받아 봐야 똑같이 죽는다. 설치본을 덮어씌우는 수밖에 없다.
      const broken = current?.embed?.kind === 'runtime'
        || current?.download.error_kind === 'runtime';
      if (window.api?.installOllama && broken) {
        setInstallNote('실행 환경이 손상돼 다시 설치합니다…');
        const result = await window.api.installOllama({ repair: true });
        setInstallNote(result.detail);
        current = (await refresh()) ?? current;
      }

      // 3) 이 PC 구성대로 모델을 받는다. 고른 모델이 있으면 함께 받는다.
      //    이미 받는 중이면 그대로 둔다 — 겹쳐 부르면 409만 돌아온다.
      if (current?.ollama.running && !current.download.running) {
        const note = await startModelDownload(chosenModel ? [chosenModel] : []);
        if (note) setInstallNote(note);
        await refresh();
        return;
      }
      if (current?.download.running) return;   // 이미 받는 중 — 정상

      // 여기까지 왔다는 것은 아무 일도 못 했다는 뜻이다. 말없이 끝내지 않는다.
      if (!current) {
        setError('앱 내부 구성 요소에 연결할 수 없습니다. 앱을 껐다 다시 열어 주세요.');
      } else {
        setWaitingForRuntime(true);
      }
    } catch (exception) {
      setError((exception as Error).message);
    } finally {
      setBusy(false);
    }
  }, [status, chosenModel, refresh]);

  // 실행 환경이 올라오면 기다리던 준비를 이어서 한다. 어떤 경로로 설치됐든
  // (무인 설치·무설치본·사용자 직접) 폴링이 발견하는 순간 다음 단계로 넘어간다.
  useEffect(() => {
    if (!waitingForRuntime || busy) return;
    if (!status?.ollama.running) return;

    setWaitingForRuntime(false);
    void runFullSetup();
  }, [waitingForRuntime, busy, status?.ollama.running, runFullSetup]);

  // 준비가 안 된 채 앱이 뜨면 **버튼 없이** 전 과정을 바로 시작한다.
  // "설치 파일 하나 받아 실행하면 나머지는 알아서"가 이 앱의 약속이다.
  //
  // 실행당 한 번만 자동 시도한다. 실패가 반복되는 PC에서 무한히 재시도하며
  // 트래픽을 태우지 않기 위해서다 — 그 뒤로는 [다시 시도]가 같은 일을 한다.
  const autoSetupTried = useRef(false);
  useEffect(() => {
    if (autoSetupTried.current || busy || forced) return;
    if (backend.status !== 'ready' && backend.status !== 'external') return;
    if (!status || status.ready) return;
    if (status.download.running) return;   // 지난 실행이 걸어 둔 다운로드가 도는 중

    autoSetupTried.current = true;
    void runFullSetup();
  }, [status, busy, forced, backend.status, runFullSetup]);

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
  // 실행 환경이 모델을 못 돌리는 상태. 모델을 더 받는 것으로는 해결되지 않는다.
  const runtimeBroken = status?.embed?.kind === 'runtime'
    || download?.error_kind === 'runtime';
  // 모델은 다 받았는데 검색이 안 도는 상태.
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

  // 단계별 완료 여부. 진행 중인 단계 하나에 스피너를 돌린다.
  const stepDone = [
    backend.status === 'ready' || backend.status === 'external',
    (status?.ollama.running ?? false) && !runtimeBroken,
    (status?.missing_required.length ?? 1) === 0,
    status?.embed?.usable ?? false,
  ];
  const working = busy || Boolean(download?.running) || waitingForRuntime || status === null;
  const activeStep = working ? stepDone.findIndex((done) => !done) : -1;

  // 실패해서 사람 손이 필요한 상태에만 버튼을 보여 준다.
  const failed = Boolean(error || download?.error) || backend.status === 'failed';

  return (
    <div className="flex h-screen items-center justify-center overflow-y-auto bg-[#F8F9FA] dark:bg-[#0d0d13] p-8">
      <div className="my-auto w-[34rem] rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#16161e] p-8 shadow-sm">
        <div className="text-lg font-bold text-gray-800 dark:text-gray-100">LocalFile AI 준비</div>
        <p className="mt-1 text-[12px] leading-relaxed text-gray-500 dark:text-gray-400">
          처음 한 번만 필요한 과정이고, 전부 자동으로 진행됩니다 — 그냥
          기다리시면 됩니다. 모든 처리는 이 PC 안에서만 이뤄지며, 문서 내용이
          밖으로 나가지 않습니다.
        </p>

        <div className="mt-6 space-y-3">
          <Step
            label="앱 시작"
            done={stepDone[0]}
            active={activeStep === 0}
            failed={backend.status === 'failed'}
            detail={backend.detail}
          />
          <Step
            label="문서 분석 도구 준비"
            done={stepDone[1]}
            active={activeStep === 1}
            failed={runtimeBroken}
            detail={
              status === null
                ? ''
                : runtimeBroken
                  // 떠 있는 것과 멀쩡한 것은 다르다. 실행 파일이 빠진 설치가 실제로 있었다.
                  ? '설치가 손상돼 있어 자동으로 다시 설치합니다.'
                  : status.ollama.running
                    ? '준비 완료'
                    : waitingForRuntime || busy
                      ? '문서를 분석하는 데 필요한 도구를 설치하는 중입니다…'
                      : '자동으로 설치합니다.'
            }
          />
          <Step
            label="AI 모델 내려받기"
            done={stepDone[2]}
            active={activeStep === 2}
            detail={
              status === null
                ? ''
                : status.missing_required.length === 0
                  ? '준비 완료'
                  : `문서를 이해하는 모델 ${status.missing_required.length}개를 받습니다 (약 ${pendingGb.toFixed(1)}GB)`
            }
          />
          {/* 모델을 받았다고 그 PC에서 도는 것은 아니다. 실제로 한 건 처리해
              보고 그 결과를 보여 준다 — 이 확인이 없던 시절, 검색이 죽은 채로
              준비 완료를 통과한 PC가 실제로 있었다. */}
          <Step
            label="검색 기능 확인"
            done={stepDone[3]}
            active={activeStep === 3}
            failed={Boolean(status?.embed && !status.embed.usable && status.embed.detail)}
            detail={
              status === null
                ? ''
                : embedBlocked
                  ? status.embed.detail
                  : status.embed?.usable
                    ? '정상 동작합니다'
                    : '모델을 받은 뒤 실제로 검색해 봅니다.'
            }
          />
        </div>

        {/* 모델 선택 — 설정에서 다시 열었을 때만. 첫 설치는 사양에 맞춰 자동이다. */}
        {forced && status && !download?.running && (
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
                  ? `검색·분류 모델(${embedModel.approx_gb}GB)은 준비돼 있습니다.`
                  : `검색·분류 모델(${embedModel.approx_gb}GB)은 선택과 무관하게 함께 받습니다.`}
              </p>
            )}
          </div>
        )}

        {/* 버튼 자리에는 진행 상황이 온다. 순서대로: 설치 파일 내려받기(측정 가능)
            → 모델 다운로드(측정 가능) → 그 밖의 작업(측정 불가, 흐르는 바). */}
        {installing && (
          <ProgressBar label="설치 파일 내려받는 중" percent={installPercent} />
        )}

        {download?.running && (
          <>
            <ProgressBar label="AI 모델 내려받는 중" percent={download.overall} />
            <p className="mt-2 text-[11px] text-gray-400 dark:text-gray-500">
              네트워크 속도에 따라 몇 분에서 수십 분이 걸립니다. 창을 닫지 마세요.
            </p>
          </>
        )}

        {!installing && !download?.running && !failed && (working || !status) && (
          <IndeterminateBar
            label={
              status === null
                ? '준비 상황을 확인하는 중입니다…'
                : waitingForRuntime
                  ? '문서 분석 도구가 준비되기를 기다리는 중입니다… (끝나면 자동으로 이어집니다)'
                  : '준비를 진행하는 중입니다…'
            }
          />
        )}

        {/* 백엔드가 죽으면 화면은 멀쩡해 보이는 채로 굳는다. 반드시 말해 준다. */}
        {backendUnreachable && (
          <div className="mt-4 rounded-lg bg-red-50 dark:bg-red-500/15 px-3 py-2 text-[11px] leading-relaxed text-red-600">
            앱 내부 연결이 끊어졌습니다. 화면에 보이는 정보가 최신이 아닐 수
            있습니다. 앱을 껐다 다시 열어 주세요.
          </div>
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

        {/* 버튼은 사람 손이 필요할 때만 나온다 — 실패했거나, 설정에서 수동으로 연 경우. */}
        {((failed && !busy) || forced) && !download?.running && (
          <div className="mt-6 flex gap-2">
            <button
              onClick={() => void runFullSetup()}
              disabled={busy}
              className="flex-1 rounded-lg bg-indigo-600 px-4 py-2.5 text-[12px] font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {busy
                ? '준비하는 중…'
                : forced && !failed
                  ? pendingGb > 0
                    ? `선택한 구성으로 받기 (약 ${pendingGb.toFixed(1)}GB)`
                    : '준비 다시 하기'
                  : '다시 시도'}
            </button>
          </div>
        )}

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

/** 진행률을 잴 수 없는 작업용 — 멈춘 게 아니라는 것만 보여 주면 된다. */
function IndeterminateBar({ label }: { label: string }) {
  return (
    <div className="mt-6">
      <div className="text-[11px] text-gray-500 dark:text-gray-400">{label}</div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-white/10">
        <div className="h-full w-1/3 animate-[slide_1.2s_ease-in-out_infinite] rounded-full bg-indigo-400" />
      </div>
      {/* tailwind 설정을 건드리지 않고 keyframes를 정의한다 */}
      <style>{`@keyframes slide { 0% { margin-left: -33%; } 100% { margin-left: 100%; } }`}</style>
    </div>
  );
}

function Step({
  label,
  done,
  active = false,
  failed = false,
  detail,
}: {
  label: string;
  done: boolean;
  /** 지금 이 단계를 진행하는 중 — 왼쪽 동그라미가 돈다 */
  active?: boolean;
  failed?: boolean;
  detail: string;
}) {
  return (
    <div className="flex items-start gap-3">
      {failed ? (
        <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-red-100 text-[11px] font-bold text-red-600">
          ✕
        </div>
      ) : done ? (
        <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-green-100 text-[11px] font-bold text-green-600">
          ✓
        </div>
      ) : active ? (
        <div className="flex h-5 w-5 shrink-0 items-center justify-center">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
        </div>
      ) : (
        <div className="flex h-5 w-5 shrink-0 items-center justify-center">
          <span className="h-2 w-2 rounded-full bg-gray-300 dark:bg-gray-600" />
        </div>
      )}
      <div className="min-w-0">
        <div className="text-[12px] font-bold text-gray-700 dark:text-gray-200">{label}</div>
        {detail && <div className="text-[11px] text-gray-500 dark:text-gray-400">{detail}</div>}
      </div>
    </div>
  );
}
