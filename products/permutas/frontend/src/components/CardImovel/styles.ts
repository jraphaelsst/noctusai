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
    padding: ${spacing.xs};
    transition: color 0.2s ease;

    &:hover {
      color: ${color.primary};
    }
  }
`

export const CardBadge = styled.span`
  display: inline-block;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: ${color.primary};
  color: ${color.textInverse};
  margin-bottom: ${spacing.sm};
  width: fit-content;
`

export const Ref = styled.h2`
  font-size: 1.25rem;
  font-weight: 600;
  color: ${color.secondary};
  margin-bottom: ${spacing.xs};
`

export const Condominio = styled.h3`
  font-size: 1rem;
  font-weight: 500;
  color: ${color.text};
  margin-bottom: ${spacing.xs};
`

export const Corretor = styled.p`
  font-size: 13px;
  color: ${color.textLight};
  margin-bottom: ${spacing.xs};
  display: flex;
  align-items: center;
  gap: ${spacing.xs};
`

export const Tipo = styled.p`
  font-size: 12px;
  color: ${color.textMuted};
  margin-bottom: ${spacing.lg};
  text-transform: uppercase;
  letter-spacing: 0.05em;
`

export const Valor = styled.div`
  font-size: 1.5rem;
  font-weight: 600;
  color: ${color.success};
  margin-top: auto;
  padding-top: ${spacing.md};
  border-top: 1px solid ${color.border};
`
