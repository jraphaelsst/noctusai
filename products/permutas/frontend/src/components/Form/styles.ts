import { styled } from 'styled-components'
import { color, spacing } from '../../styles'

export const FormContainer = styled.form`
  display: flex;
  flex-direction: column;
  width: 100%;
`

export const Title = styled.h1`
  font-size: 1.75rem;
  font-weight: 700;
  color: ${color.secondary};
  margin-bottom: ${spacing.xl};
  text-align: center;
`

export const FormGroup = styled.div`
  margin-bottom: ${spacing.md};
`

export const Label = styled.label`
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: ${color.text};
  margin-bottom: ${spacing.xs};
`
