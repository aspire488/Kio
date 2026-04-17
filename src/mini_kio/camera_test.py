import cv2



print("Starting camera test...")



# Try DirectShow backend for Windows

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)



if not cap.isOpened():

    print("Camera not accessible. Trying alternative index...")



    # Try second index

    cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)



if not cap.isOpened():

    print("ERROR: No camera detected.")

    exit()



print("Camera opened successfully.")



while True:

    ret, frame = cap.read()



    if not ret:

        print("Failed to grab frame.")

        break



    cv2.imshow("KIO Camera Test", frame)



    # press Q to quit

    if cv2.waitKey(1) & 0xFF == ord("q"):

        break



cap.release()

cv2.destroyAllWindows()



print("Camera closed.")
