import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { JourneyWizard, type JourneyStep } from './JourneyWizard';

afterEach(cleanup);

const mk = (over: Partial<JourneyStep>[] = []): JourneyStep[] =>
  ['a', 'b', 'c'].map((id, i) => ({
    id, title: `Step ${id}`, category: i < 2 ? 'Base' : 'Final',
    content: <p>body-{id}</p>, ...(over[i] ?? {}),
  }));

describe('JourneyWizard', () => {
  it('navigates forward/back and reports progress', () => {
    const onStepChange = vi.fn();
    render(<JourneyWizard steps={mk()} onComplete={vi.fn()} onStepChange={onStepChange} />);
    expect(screen.getByText('Etapa 1 de 3')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '33');
    fireEvent.click(screen.getByText('Continuar'));
    expect(screen.getByText('body-b')).toBeInTheDocument();
    expect(onStepChange).toHaveBeenCalledWith('b', 1);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '67');
    fireEvent.click(screen.getByText('Voltar'));
    expect(screen.getByText('body-a')).toBeInTheDocument();
  });

  it('blocks on failed validation and shows the message', () => {
    render(<JourneyWizard steps={mk([{ validate: () => 'Preencha o nome' }])} onComplete={vi.fn()} />);
    fireEvent.click(screen.getByText('Continuar'));
    expect(screen.getByRole('alert')).toHaveTextContent('Preencha o nome');
    expect(screen.getByText('body-a')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /Step c/ }));
    expect(screen.getByText('body-a')).toBeInTheDocument();
  });

  it('skips an optional step in one click and completes', () => {
    const onComplete = vi.fn();
    render(<JourneyWizard steps={mk([{}, { optional: true }])} onComplete={onComplete} />);
    fireEvent.click(screen.getByText('Continuar'));
    fireEvent.click(screen.getByText('Pular etapa'));
    expect(screen.getByText('body-c')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Concluir'));
    expect(onComplete).toHaveBeenCalledWith({ completed: ['a', 'c'], skipped: ['b'] });
  });

  it('renders subtabs and switches them', () => {
    const subtabs = [{ id: 's1', title: 'One', content: <i>sub-one</i> }, { id: 's2', title: 'Two', content: <i>sub-two</i> }];
    render(<JourneyWizard steps={mk([{ subtabs }])} onComplete={vi.fn()} />);
    expect(screen.getByText('sub-one')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Two' }));
    expect(screen.getByText('sub-two')).toBeInTheDocument();
  });

  it('supports controlled step and keyboard navigation', () => {
    const onStepChange = vi.fn();
    render(<JourneyWizard steps={mk()} currentStepId="b" onComplete={vi.fn()} onStepChange={onStepChange} />);
    expect(screen.getByText('body-b')).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole('tab', { name: /Step b/ }), { key: 'ArrowRight' });
    expect(onStepChange).toHaveBeenCalledWith('c', 2);
  });

  it('drops animation classes under prefers-reduced-motion', () => {
    const mm = vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() });
    vi.stubGlobal('matchMedia', mm);
    window.matchMedia = mm as unknown as typeof window.matchMedia;
    const { container } = render(<JourneyWizard steps={mk()} onComplete={vi.fn()} />);
    expect(container.firstElementChild).toHaveAttribute('data-reduced-motion', 'true');
    expect(container.innerHTML).not.toContain('animate-in');
    expect(container.innerHTML).not.toContain('transition-all');
    vi.unstubAllGlobals();
  });
});
