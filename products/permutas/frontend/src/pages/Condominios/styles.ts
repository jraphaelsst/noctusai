import { styled } from 'styled-components'
import { color, spacing, breakpoints } from '../../styles'

export const Container = styled.div`
  padding: ${spacing.lg};
`

export const CondominiosGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: ${spacing.lg};

  @media (max-width: ${breakpoints.desktop}) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: ${breakpoints.tablet}) {
    grid-template-columns: 1fr;
  }
`

export const FilterSection = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${spacing.sm};
  margin-bottom: ${spacing.lg};
`

export const FilterButton = styled.button<{ active?: boolean }>`
  padding: ${spacing.sm} ${spacing.md};
  border: 1px solid ${(props) => (props.active ? color.primary : color.border)};
  background: ${(props) => (props.active ? color.primary : 'transparent')};
  color: ${(props) => (props.active ? color.textInverse : color.text)};
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    border-color: ${color.primary};
  }
`
