import { memo } from 'react'
import styled, { keyframes } from 'styled-components'
import { color } from '../../styles'

const spin = keyframes`
  to {
    transform: rotate(360deg);
  }
`

const SpinnerWrapper = styled.div`
  display: inline-block;
  width: 24px;
  height: 24px;
  border: 2px solid ${color.border};
  border-top-color: ${color.primary};
  border-radius: 50%;
  animation: ${spin} 0.8s linear infinite;
`

const SpinnerContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 32px;
  width: 100%;
`

type SpinnerProps = {
  size?: number
}

export const Spinner = memo(({ size = 24 }: SpinnerProps) => (
  <SpinnerWrapper style={{ width: size, height: size }} />
))

export const LoadingScreen = memo(() => (
  <SpinnerContainer>
    <Spinner size={32} />
  </SpinnerContainer>
))

export default Spinner
