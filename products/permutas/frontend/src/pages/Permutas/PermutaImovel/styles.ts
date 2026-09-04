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

export const Tipo = styled.span`
  display: inline-flex;
  align-items: center;
  padding: ${spacing.xs} ${spacing.md};
  background: ${color.primary};
  color: ${color.textInverse};
  font-size: 13px;
  font-weight: 500;
  width: fit-content;
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
  font-size: 2rem;
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

export const CardGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: ${spacing.xl};

  @media (max-width: ${breakpoints.tablet}) {
    grid-template-columns: 1fr;
  }
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
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: ${spacing.xl};
  margin-top: ${spacing.xl};

  @media (max-width: ${breakpoints.tablet}) {
    grid-template-columns: 1fr;
  }
`

export const MatchSection = styled.div`
  background: ${color.cardBg};
  padding: ${spacing.xl};
  border: 1px solid ${color.border};
`

export const MatchSectionTitle = styled.h3`
  font-size: 1rem;
  font-weight: 600;
  color: ${color.secondary};
  margin-bottom: ${spacing.lg};
`

export const MatchCard = styled.div`
  padding: ${spacing.md};
  border: 1px solid ${color.border};
  margin-bottom: ${spacing.md};
  transition: all 0.2s ease;
  background: ${color.background};
  cursor: pointer;

  &:hover {
    border-color: ${color.success};
  }

  &:last-child {
    margin-bottom: 0;
  }
`

export const MatchBadge = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${spacing.xs};
  padding: 4px 10px;
  background: ${color.success};
  color: ${color.textInverse};
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: ${spacing.sm};
`

export const MatchCardTitle = styled.h4`
  font-size: 1rem;
  font-weight: 600;
  color: ${color.text};
  margin-bottom: ${spacing.sm};
`

export const MatchCardDetail = styled.p`
  font-size: 14px;
  color: ${color.textLight};
  margin-bottom: ${spacing.xs};
`

export const MatchCardValue = styled.p`
  font-size: 1.25rem;
  font-weight: 600;
  color: ${color.success};
  margin-top: ${spacing.sm};
`

export const EmptyMessage = styled.p`
  color: ${color.textLight};
  text-align: center;
  padding: ${spacing.xl};
`

export const InteresseSection = styled.div`
  margin-top: ${spacing.xxl};
`

export const InteresseSectionHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: ${spacing.lg};
`

export const AddButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: ${spacing.xs};
  padding: ${spacing.sm} ${spacing.lg};
  background: ${color.success};
  color: white;
  border: none;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  
  &:hover {
    opacity: 0.9;
  }
`

export const InteresseTable = styled.table`
  width: 100%;
  border-collapse: collapse;
  background: ${color.cardBg};
  border: 1px solid ${color.border};
`

export const InteresseTableHeader = styled.thead`
  background: ${color.background};
  
  th {
    padding: ${spacing.md};
    text-align: left;
    font-size: 13px;
    font-weight: 600;
    color: ${color.text};
    border-bottom: 1px solid ${color.border};
  }
`

export const InteresseTableBody = styled.tbody`
  tr {
    border-bottom: 1px solid ${color.border};
    
    &:last-child {
      border-bottom: none;
    }
    
    &:hover {
      background: ${color.background};
    }
  }
  
  td {
    padding: ${spacing.md};
    font-size: 14px;
    color: ${color.textLight};
  }
`

export const TableActions = styled.div`
  display: flex;
  gap: ${spacing.xs};
`

export const TableActionButton = styled.button<{ $variant?: 'edit' | 'delete' }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
  
  ${({ $variant }) => $variant === 'delete' ? `
    background: ${color.danger};
    color: white;
  ` : `
    background: ${color.primary};
    color: white;
  `}
  
  &:hover {
    opacity: 0.8;
  }
`
