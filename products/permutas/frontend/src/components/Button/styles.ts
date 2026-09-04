import { styled, css } from 'styled-components'
import { color, spacing } from '../../styles'

const baseButtonStyles = css`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: ${spacing.sm};
  padding: 12px 24px;
  margin: 2px 0;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition: all 0.2s ease;
  border: none;
  text-decoration: none;

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`

export const ButtonContainer = styled.button`
  ${baseButtonStyles}
  background: ${color.primary};
  color: ${color.textInverse};

  &:hover:not(:disabled) {
    background: ${color.primaryLight};
  }

  &:active:not(:disabled) {
    background: ${color.primaryDark};
  }

  a {
    color: inherit;
    text-decoration: none;
  }
`

export const ButtonOutline = styled.button`
  ${baseButtonStyles}
  background: transparent;
  color: ${color.primary};
  border: 1px solid ${color.primary};

  &:hover:not(:disabled) {
    background: ${color.primary};
    color: ${color.textInverse};
  }
`

export const ButtonSecondary = styled.button`
  ${baseButtonStyles}
  background: ${color.backgroundDark};
  color: ${color.text};
  border: 1px solid ${color.border};

  &:hover:not(:disabled) {
    background: ${color.border};
  }
`

export const ButtonDanger = styled.button`
  ${baseButtonStyles}
  background: ${color.danger};
  color: ${color.textInverse};

  &:hover:not(:disabled) {
    opacity: 0.9;
  }
`

export const ButtonSuccess = styled.button`
  ${baseButtonStyles}
  background: ${color.success};
  color: ${color.textInverse};

  &:hover:not(:disabled) {
    opacity: 0.9;
  }
`
