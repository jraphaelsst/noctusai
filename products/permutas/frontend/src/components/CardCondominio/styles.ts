import { styled } from 'styled-components'
import { color, spacing } from '../../styles'

export const CardContainer = styled.div`
  position: relative;
  height: fit-content;
  width: 100%;
  background-color: ${color.cardBg};
  padding: ${spacing.lg};
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  border: 1px solid ${color.border};
  transition: all 0.2s ease;

  &:hover {
    border-color: ${color.primary};
  }
`

export const Icons = styled.div`
  position: absolute;
  top: ${spacing.md};
  right: ${spacing.md};
  display: flex;
  gap: ${spacing.sm};

  i {
    cursor: pointer;
    color: ${color.textMuted};
    transition: color 0.2s ease;

    &:hover {
      color: ${color.primary};
    }
  }
`

export const Bairro = styled.p`
  font-size: 13px;
  color: ${color.textLight};
  margin-bottom: ${spacing.xs};
`

export const Nome = styled.h2`
  font-size: 1.25rem;
  font-weight: 600;
  color: ${color.secondary};
  margin-bottom: ${spacing.sm};
`

export const Endereco = styled.h3`
  font-size: 14px;
  font-weight: 500;
  color: ${color.text};
  margin-bottom: ${spacing.xs};
`

export const Km = styled.p`
  font-size: 13px;
  color: ${color.textMuted};
  margin-bottom: ${spacing.lg};
`

export const Valor = styled.div`
  font-size: 14px;
  color: ${color.textLight};
  margin-bottom: ${spacing.sm};
`
