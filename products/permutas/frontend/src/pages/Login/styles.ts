import { styled } from 'styled-components'
import { breakpoints, color, spacing } from '../../styles'

export const FormContainer = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 100vh;
  width: 100%;
  background: ${color.primary};

  @media (max-width: ${breakpoints.tablet}) {
    grid-template-columns: 1fr;
  }
`

export const LogoSection = styled.div`
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: ${spacing.xxl};
  background: ${color.primaryDark};

  img {
    width: 80%;
    max-width: 400px;
    filter: brightness(0) invert(1);
    margin-bottom: ${spacing.xl};
  }

  @media (max-width: ${breakpoints.tablet}) {
    display: none;
  }
`

export const FormSection = styled.div`
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: ${spacing.xxl};
`

export const FormCard = styled.div`
  width: 100%;
  max-width: 420px;
  background: ${color.cardBg};
  padding: ${spacing.xxl};
`

export const FormTitle = styled.h1`
  font-size: 1.75rem;
  font-weight: 600;
  color: ${color.secondary};
  margin-bottom: ${spacing.sm};
  text-align: center;
`

export const FormSubtitle = styled.p`
  color: ${color.textLight};
  text-align: center;
  margin-bottom: ${spacing.xl};
  font-size: 14px;
`
