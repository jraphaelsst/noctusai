/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, act, cleanup } from '@testing-library/react';
import { VoiceAnswerInput } from './VoiceAnswerInput';
import { pickAudioMime } from '../hooks/useAudioRecorder';

let supported: string[] = [];
let instances: FakeRecorder[] = [];
const trackStop = vi.fn();

class FakeRecorder {
  state: 'inactive' | 'recording' = 'inactive';
  mimeType: string;
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  static isTypeSupported = (m: string) => supported.includes(m);
  constructor(_s: unknown, opts?: { mimeType?: string }) {
    this.mimeType = opts?.mimeType ?? '';
    instances.push(this);
  }
  start() { this.state = 'recording'; }
  stop() { this.state = 'inactive'; this.onstop?.(); }
  push(bytes: number) { this.ondataavailable?.({ data: new Blob([new Uint8Array(bytes)]) }); }
}

function setMedia(getUserMedia: unknown) {
  Object.defineProperty(navigator, 'mediaDevices', { value: getUserMedia ? { getUserMedia } : undefined, configurable: true });
}
const okStream = () => vi.fn().mockResolvedValue({ getTracks: () => [{ stop: trackStop }] });

async function click(name: RegExp) {
  await act(async () => { fireEvent.click(screen.getByRole('button', { name })); });
}

beforeEach(() => {
  vi.useFakeTimers();
  supported = ['audio/webm;codecs=opus'];
  instances = [];
  trackStop.mockClear();
  vi.stubGlobal('MediaRecorder', FakeRecorder);
  setMedia(okStream());
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('mime fallback', () => {
  it.each([
    [['audio/webm;codecs=opus', 'audio/webm'], 'audio/webm;codecs=opus'],
    [['audio/webm', 'audio/mp4'], 'audio/webm'],
    [['audio/mp4', 'audio/mpeg'], 'audio/mp4'],
    [['audio/mpeg'], 'audio/mpeg'],
  ])('picks %j -> %s', (sup, expected) => {
    supported = sup;
    expect(pickAudioMime()).toBe(expected);
  });
  it('returns null when nothing is supported', () => {
    supported = [];
    expect(pickAudioMime()).toBeNull();
  });
});

describe('VoiceAnswerInput', () => {
  it('records, shows timer, delivers blob on stop and releases tracks', async () => {
    const onRecorded = vi.fn();
    render(<VoiceAnswerInput onRecorded={onRecorded} />);
    await click(/gravar resposta/i);
    expect(instances[0].mimeType).toBe('audio/webm;codecs=opus');
    act(() => { instances[0].push(100); vi.advanceTimersByTime(3000); });
    expect(screen.getByTestId('voice-answer-timer')).toHaveTextContent('00:03');
    await click(/parar/i);
    expect(onRecorded).toHaveBeenCalledTimes(1);
    const [blob, mime, secs] = onRecorded.mock.calls[0];
    expect(blob.size).toBe(100);
    expect(mime).toBe('audio/webm;codecs=opus');
    expect(secs).toBe(3);
    expect(trackStop).toHaveBeenCalled();
  });

  it('auto-stops at maxSeconds and still delivers', async () => {
    const onRecorded = vi.fn();
    render(<VoiceAnswerInput onRecorded={onRecorded} maxSeconds={2} />);
    await click(/gravar resposta/i);
    act(() => { instances[0].push(10); vi.advanceTimersByTime(2500); });
    expect(instances[0].state).toBe('inactive');
    expect(onRecorded).toHaveBeenCalledTimes(1);
  });

  it('permission denied shows pt-BR message', async () => {
    setMedia(vi.fn().mockRejectedValue(new Error('denied')));
    render(<VoiceAnswerInput onRecorded={vi.fn()} />);
    await click(/gravar resposta/i);
    expect(screen.getByRole('alert')).toHaveTextContent('Erro ao acessar o microfone. Verifique as permissões!');
  });

  it('unsupported (no getUserMedia) shows pt-BR message', async () => {
    setMedia(undefined);
    render(<VoiceAnswerInput onRecorded={vi.fn()} />);
    await click(/gravar resposta/i);
    expect(screen.getByRole('alert')).toHaveTextContent('Ops! Parece que seu navegador não tem suporte para esse recurso, tente outro!');
  });

  it('unsupported (no mime) shows pt-BR message', async () => {
    supported = [];
    render(<VoiceAnswerInput onRecorded={vi.fn()} />);
    await click(/gravar resposta/i);
    expect(screen.getByRole('alert')).toHaveTextContent('Ops!');
  });

  it('size guard stops, discards and errors too_large', async () => {
    const onRecorded = vi.fn();
    render(<VoiceAnswerInput onRecorded={onRecorded} maxBytes={50} />);
    await click(/gravar resposta/i);
    act(() => { instances[0].push(80); });
    expect(instances[0].state).toBe('inactive');
    expect(onRecorded).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Gravação muito longa');
    expect(trackStop).toHaveBeenCalled();
  });

  it('releases tracks and stops recorder on unmount', async () => {
    const onRecorded = vi.fn();
    const { unmount } = render(<VoiceAnswerInput onRecorded={onRecorded} />);
    await click(/gravar resposta/i);
    unmount();
    expect(instances[0].state).toBe('inactive');
    expect(trackStop).toHaveBeenCalled();
    expect(onRecorded).not.toHaveBeenCalled();
  });

  it('disabled blocks recording', async () => {
    const gum = okStream();
    setMedia(gum);
    render(<VoiceAnswerInput onRecorded={vi.fn()} disabled />);
    expect(screen.getByRole('button')).toBeDisabled();
  });
});
