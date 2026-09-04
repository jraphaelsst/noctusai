import { styled } from 'styled-components'
import { color, spacing, breakpoints } from '../../../styles'
import { fadeInForm, fadeInInput } from '../../../utils/keyframes'

export const Form = styled.div`
  background-color: ${color.cardBg};
  width: 100%;
  margin: ${spacing.md} 0;
  border: 1px solid ${color.border};
  display: none;
  transition: all 0.3s ease;
  overflow: hidden;

  &.active {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: ${spacing.lg};
    padding: ${spacing.xl};
    animation: ${fadeInForm} 0.5s ease forwards;

    @media (max-width: ${breakpoints.desktop}) {
      grid-template-columns: repeat(2, 1fr);
    }

    @media (max-width: ${breakpoints.tablet}) {
      grid-template-columns: 1fr;
    }
  }
`

export const FormField = styled.div`
  display: flex;
  flex-direction: column;

  &.activeInput {
    animation: ${fadeInInput} 0.5s ease-in;
  }
`

export const FormLabel = styled.label`
  font-size: 13px;
  font-weight: 500;
  color: ${color.text};
  margin-bottom: ${spacing.xs};
`

export const FormInteresse = styled.div`
  background-color: ${color.cardBg};
  width: 100%;
  margin: ${spacing.md} 0;
  border: 1px solid ${color.border};
  display: none;
  transition: all 0.3s ease;
  overflow: hidden;

  &.active {
    display: flex;
    flex-direction: column;
    gap: ${spacing.lg};
    padding: ${spacing.xl};
    animation: ${fadeInForm} 0.5s ease forwards;
  }

  p {
    font-size: 13px;
    color: ${color.textMuted};
    margin-top: ${spacing.md};
  }
`

export const FormInput = styled.input`
  padding: 10px 14px;
  border: 1px solid ${color.border};
  background: ${color.cardBg};
  color: ${color.text};
  font-size: 14px;
  transition: border-color 0.2s ease;

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }

  &::placeholder {
    color: ${color.textMuted};
  }
`

export const Select = styled.select`
  padding: 10px 14px;
  border: 1px solid ${color.border};
  background: ${color.cardBg};
  color: ${color.text};
  font-size: 14px;
  cursor: pointer;
  transition: border-color 0.2s ease;

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }
`

export const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
  margin: ${spacing.lg} 0;
  background: ${color.cardBg};
  border: 1px solid ${color.border};
`

export const TableHead = styled.th`
  padding: ${spacing.md};
  text-align: left;
  font-size: 12px;
  font-weight: 500;
  color: ${color.textLight};
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: ${color.backgroundDark};
  border-bottom: 1px solid ${color.border};
`

export const TableRow = styled.tr`
  transition: background 0.2s ease;

  &:hover {
    background: ${color.backgroundDark};
  }

  &:not(:last-child) {
    border-bottom: 1px solid ${color.border};
  }
`

export const TableCell = styled.td`
  padding: ${spacing.md};
  font-size: 14px;
  color: ${color.text};
  border-bottom: 1px solid ${color.border};
`

export const TableTitle = styled.h2`
  font-size: 1.125rem;
  font-weight: 600;
  color: ${color.secondary};
  margin: ${spacing.xl} 0 ${spacing.md} 0;
  display: flex;
  align-items: center;
  gap: ${spacing.sm};

  &:before {
    content: '';
    width: 3px;
    height: 20px;
    background: ${color.primary};
  }
`

export const FormActions = styled.div`
  display: flex;
  gap: ${spacing.md};
  margin-top: ${spacing.lg};
  padding-top: ${spacing.lg};
  border-top: 1px solid ${color.border};
`

export const InteresseCard = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${spacing.md};
  padding: ${spacing.md};
  background: ${color.backgroundDark};
  margin-bottom: ${spacing.md};
`

export const ActionIcon = styled.button`
  background: none;
  border: none;
  cursor: pointer;
  padding: ${spacing.xs};
  color: ${color.textLight};
  font-size: 14px;
  transition: color 0.2s ease;

  &:hover {
    color: ${color.primary};
  }

  &.delete:hover {
    color: ${color.danger};
  }
`

export const ActionCell = styled.td`
  padding: ${spacing.sm};
  text-align: center;
  white-space: nowrap;
  border-bottom: 1px solid ${color.border};
`
