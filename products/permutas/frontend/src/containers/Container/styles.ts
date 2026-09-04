import { styled } from 'styled-components'
import { color, spacing, breakpoints } from '../../styles'

export const GlobalContainer = styled.div`
  max-width: 1200px;
  width: 100%;
  background-color: ${color.cardBg};
  margin: 0 auto;
  color: ${color.text};
  padding: ${spacing.xl};
  border-radius: 0;
  box-shadow: none;
  border: none;
  min-height: calc(100vh - 56px);

  @media (max-width: ${breakpoints.tablet}) {
    margin: 0 auto;
    padding: ${spacing.md};
    border-radius: 0;
  }

  @media (max-width: 480px) {
    padding: ${spacing.sm};
  }
`

export const Title = styled.h1`
  font-size: 1.75rem;
  font-weight: 700;
  color: ${color.secondary};
  padding-bottom: ${spacing.lg};
  margin-bottom: ${spacing.lg};
  text-align: center;
  border-bottom: 2px solid ${color.border};
`
