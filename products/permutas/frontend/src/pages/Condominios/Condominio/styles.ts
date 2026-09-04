import { styled } from 'styled-components'
import { color, spacing, breakpoints } from '../../../styles'

export const Container = styled.div`
  width: 100%;
  min-height: 100vh;
  background: ${color.background};
`

export const Banner = styled.div`
  background: ${color.primary};
  padding: ${spacing.xxl};
  display: flex;
  gap: ${spacing.xl};
  align-items: stretch;

  @media (max-width: ${breakpoints.tablet}) {
    flex-direction: column;
    padding: ${spacing.lg};
  }
`

export const Icon = styled.div`
  width: 120px;
  height: 120px;
  background: ${color.primaryLight};
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 2.5rem;
`

export const Infos = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: ${spacing.lg};
  background: ${color.cardBg};
`

export const Nome = styled.h1`
  font-size: 1.75rem;
  font-weight: 600;
  color: ${color.secondary};
  margin-bottom: ${spacing.md};
`

export const InfoItem = styled.p`
  font-size: 14px;
  color: ${color.textLight};
  margin-bottom: ${spacing.sm};
  display: flex;
  align-items: center;
  gap: ${spacing.sm};

  strong {
    color: ${color.text};
  }
`

export const Valor = styled.h3`
  font-size: 1.5rem;
  font-weight: 600;
  color: ${color.success};
  margin-top: ${spacing.md};
`

export const Sections = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: ${spacing.xxl} ${spacing.lg};
`

export const TituloSecao = styled.h2`
  font-size: 1.25rem;
  font-weight: 600;
  color: ${color.secondary};
  margin-bottom: ${spacing.lg};
  display: flex;
  align-items: center;
  gap: ${spacing.sm};

  &:before {
    content: '';
    width: 3px;
    height: 24px;
    background: ${color.primary};
  }
`

export const Card = styled.div`
  background: ${color.cardBg};
  padding: ${spacing.xl};
  margin-bottom: ${spacing.xl};
  border: 1px solid ${color.border};
`

export const ActionButtons = styled.div`
  display: flex;
  gap: ${spacing.sm};
  margin-top: ${spacing.lg};
`

export const ActionButton = styled.button<{ $variant?: 'edit' | 'delete' }>`
  display: inline-flex;
  align-items: center;
  gap: ${spacing.xs};
  padding: ${spacing.sm} ${spacing.lg};
  border: none;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  
  ${({ $variant }) => $variant === 'delete' ? `
    background: ${color.danger};
    color: white;
    
    &:hover {
      opacity: 0.9;
    }
  ` : `
    background: ${color.primary};
    color: white;
    
    &:hover {
      background: ${color.primaryLight};
    }
  `}
`
