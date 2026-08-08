# 실험 010: 원자 이동 파일 시스템 호환 진단

작성일: 2026-08-08

## 지난 코드의 한계

hard link 미지원, 다른 볼륨, 권한 제한 오류가 모두 일반 `atomic_move_error`로
표시돼 사용자가 복구 방법을 알기 어려웠다.

## 변경 코드를 통한 보완점

EXDEV, EPERM, EACCES, EOPNOTSUPP, ENOTSUP을 안전 이동 미지원 오류로 분류한다.
이 경우 덮어쓸 수 있는 비원자 이동으로 자동 폴백하지 않고 원본을 보존한 채 다음
안내를 반환한다.

```text
atomic_move_unsupported: 이 위치는 안전한 파일 이동(hard link)을 지원하지 않거나
다른 드라이브입니다. 같은 로컬 드라이브 폴더를 선택하세요
```

## 실제 결과

현재 Windows 임시 파일 시스템에서 실제 hard link 이동을 실행했다.

```json
{"supported":true,"source_removed":true}
```

EXDEV 주입 테스트에서는 항목이 failed가 되고 원본 파일이 그대로 유지됐다.

## 보완 코드의 한계

사전 진단 엔드포인트는 없고 실제 적용 시 오류로 판단한다. 같은 root 아래 junction이
다른 볼륨을 가리키는 경우도 적용 순간에야 확인된다. 안전을 위해 자동 복사 폴백은
제공하지 않는다.

