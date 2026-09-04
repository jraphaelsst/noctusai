import { useDispatch, useSelector } from 'react-redux'

import { RootReducer } from '../../store'
import { closeInteresses } from '../../store/reducers/overlayInteresses'

import { FormContainer, Overlay, OverlayContainer, Title } from './styles'

type Props = {
  title: string
  children: JSX.Element[]
}

const OverlayInteressesForm = ({ title, children }: Props) => {
  const { isInteressesOpen } = useSelector(
    (state: RootReducer) => state.overlayInteresses
  )

  const dispatch = useDispatch()
  const closeForm = () => {
    dispatch(closeInteresses())
  }

  return (
    <OverlayContainer className={isInteressesOpen ? 'isOpen' : ''}>
      <FormContainer>
        <Title>{title}</Title>
        {children}
      </FormContainer>
      <Overlay onClick={closeForm} />
    </OverlayContainer>
  )
}

export default OverlayInteressesForm
