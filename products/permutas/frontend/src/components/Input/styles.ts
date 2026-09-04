import { styled } from 'styled-components'
import { color, spacing } from '../../styles'

export const InputField = styled.input`
  width: 100%;
  padding: 12px 16px;
  margin-bottom: ${spacing.md};
  border: 1px solid ${color.border};
  background-color: ${color.cardBg};
  color: ${color.text};
  font-size: 14px;
  transition: border-color 0.2s ease;

  &::placeholder {
    color: ${color.textMuted};
  }

  &:hover {
    border-color: ${color.textLight};
  }

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }

  &:disabled {
    background-color: ${color.backgroundDark};
    cursor: not-allowed;
    opacity: 0.6;
  }
`

export const TextArea = styled.textarea`
  width: 100%;
  padding: 12px 16px;
  margin-bottom: ${spacing.md};
  border: 1px solid ${color.border};
  background-color: ${color.cardBg};
  color: ${color.text};
  font-size: 14px;
  min-height: 120px;
  resize: vertical;
  transition: border-color 0.2s ease;

  &::placeholder {
    color: ${color.textMuted};
  }

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }
`

export const Select = styled.select`
  width: 100%;
  padding: 12px 16px;
  margin-bottom: ${spacing.md};
  border: 1px solid ${color.border};
  background-color: ${color.cardBg};
  color: ${color.text};
  font-size: 14px;
  cursor: pointer;
  transition: border-color 0.2s ease;

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }
`
