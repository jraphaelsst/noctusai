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

export const Avatar = styled.div`
  width: 120px;
  height: 120px;
  background: ${color.primaryLight};
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 2.5rem;
  font-weight: 600;
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

export const MatchesContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${spacing.xl};
`

export const MatchSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${spacing.md};
`

export const MatchSectionTitle = styled.h3`
  font-size: 1rem;
  font-weight: 600;
  color: ${color.text};
  padding-bottom: ${spacing.sm};
  border-bottom: 1px solid ${color.border};
`

export const CardGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: ${spacing.md};
`

export const MatchCard = styled.div`
  background: ${color.cardBg};
  border: 1px solid ${color.border};
  padding: ${spacing.lg};
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    border-color: ${color.primary};
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }
`

export const MatchBadge = styled.span`
  display: inline-block;
  background: ${color.success};
  color: white;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  margin-bottom: ${spacing.sm};
  text-transform: uppercase;
`

export const MatchCardTitle = styled.h4`
  font-size: 14px;
  font-weight: 600;
  color: ${color.text};
  margin-bottom: ${spacing.xs};
`

export const MatchCardDetail = styled.p`
  font-size: 13px;
  color: ${color.textMuted};
  margin-bottom: 2px;
`

export const MatchCardValue = styled.p`
  font-size: 14px;
  font-weight: 600;
  color: ${color.success};
  margin-top: ${spacing.sm};
`

export const EmptyMessage = styled.p`
  font-size: 14px;
  color: ${color.textMuted};
  text-align: center;
  padding: ${spacing.xl};
`
