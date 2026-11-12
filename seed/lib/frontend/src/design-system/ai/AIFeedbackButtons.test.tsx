/** The `choices` seam of AIFeedbackButtons: controlled labelled verdicts + keyboard shortcuts; thumbs path untouched. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

vi.mock('./useAIFeedback', () => ({
  useAIFeedback: () => ({ data: null }),
  useSubmitAIFeedback: () => ({ mutate: vi.fn(), isPending: false, isSuccess: false }),
}));

import { AIFeedbackButtons } from './AIFeedbackButtons';

const CHOICES = [
  { value: 'sim', label: 'Sim', shortcut: '1' },
  { value: 'nao', label: 'Não', shortcut: '2' },
];

afterEach(cleanup);

describe('AIFeedbackButtons choices seam', () => {
  it('hands the pick to onChoose and shows the selected value', () => {
    const onChoose = vi.fn();
    render(<AIFeedbackButtons output_ref="x" choices={CHOICES} selected="nao" onChoose={onChoose} />);
    fireEvent.click(screen.getByTestId('ai-choice-sim'));
    expect(onChoose).toHaveBeenCalledWith('sim');
    expect(screen.getByTestId('ai-choice-nao')).toHaveAttribute('aria-pressed', 'true');
  });

  it('binds shortcuts, ignores typing targets and modifiers, and stops when disabled', () => {
    const onChoose = vi.fn();
    const { rerender } = render(<AIFeedbackButtons output_ref="x" choices={CHOICES} onChoose={onChoose} />);
    fireEvent.keyDown(window, { key: '2' });
    expect(onChoose).toHaveBeenCalledWith('nao');
    fireEvent.keyDown(window, { key: '1', ctrlKey: true });
    const input = document.createElement('input');
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: '1' });
    expect(onChoose).toHaveBeenCalledTimes(1);
    rerender(<AIFeedbackButtons output_ref="x" choices={CHOICES} onChoose={onChoose} disabled />);
    fireEvent.keyDown(window, { key: '1' });
    expect(onChoose).toHaveBeenCalledTimes(1);
  });

  it('without choices it is still the thumbs widget', () => {
    render(<AIFeedbackButtons output_ref="x" />);
    expect(screen.getByTitle('Útil')).toBeInTheDocument();
  });
});
